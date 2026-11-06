// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Creative Live! Cam Vista IM (VF0260, 041e:4052, OV519 + OV7670):
 * sensor tuning and extra controls taken from Creative's Windows driver.
 *
 * Included from ov519.c (like w996Xcf.c). All register values come from
 * creative_tables.h, generated from V0260Vid.inf by gen_tables.py.
 *
 * "Creative Tuning" can be switched while streaming so the stock Linux
 * settings and Creative's can be compared on the same scene. When it is
 * off, the sensor gets exactly the stock norm_7670 table and the extra
 * controls below are not applied.
 */

#define CR_CID_BASE		(V4L2_CID_USER_BASE + 0xf000)
#define CR_CID_TUNING		(CR_CID_BASE + 0)
#define CR_CID_SHARP_AUTO	(CR_CID_BASE + 1)
#define CR_CID_REG		(CR_CID_BASE + 2)
#define CR_CID_VAL		(CR_CID_BASE + 3)
#define CR_CID_REG_WRITE	(CR_CID_BASE + 4)
#define CR_CID_REG_READ		(CR_CID_BASE + 5)

static void cr_write(struct sd *sd, const struct cr_regmask *t, int n)
{
	for (; n > 0; n--, t++) {
		if (t->mask == 0xff)
			i2c_w(sd, t->reg, t->val);
		else
			i2c_w_mask(sd, t->reg, t->val, t->mask);
	}
}

/*
 * Registers owned by the mode/window/frame-rate code. A live switch must
 * not touch them or the running stream breaks (e.g. QVGA window).
 */
static bool cr_live_skip(u8 reg)
{
	switch (reg) {
	case 0x03: case 0x11: case 0x12: case 0x17:
	case 0x18: case 0x19: case 0x1a: case 0x32:
		return true;
	}
	return false;
}

/* Full init at probe time (sensor reset + Creative CameraSetting) */
static void cr_init_sensor(struct sd *sd)
{
	i2c_w(sd, OV7670_R12_COM7, OV7670_COM7_RESET);
	msleep(14);
	cr_write(sd, cr_init, ARRAY_SIZE(cr_init));
}

/* WB menu index -> Creative preset (0 auto, 1 fluorescent, 2 tungsten, 3 outdoor) */
static int cr_wb_preset(s32 v)
{
	switch (v) {
	case V4L2_WHITE_BALANCE_FLUORESCENT:	return 1;
	case V4L2_WHITE_BALANCE_INCANDESCENT:	return 2;
	case V4L2_WHITE_BALANCE_DAYLIGHT:	return 3;
	default:				return 0;
	}
}

static void cr_set_exposure(struct sd *sd)
{
	bool manual = sd->cr_exp_auto->val == V4L2_EXPOSURE_MANUAL;

	if (manual) {
		cr_write(sd, cr_exp_auto_off, ARRAY_SIZE(cr_exp_auto_off));
		cr_write(sd, cr_exp[sd->cr_exp->val], ARRAY_SIZE(cr_exp[0]));
		cr_write(sd, cr_gain[sd->cr_gain->val], ARRAY_SIZE(cr_gain[0]));
	} else {
		/* enabling auto also resets the AEC window (9f/a0) */
		cr_write(sd, cr_exp_auto_on, ARRAY_SIZE(cr_exp_auto_on));
	}
	/* backlight compensation lives in the same AEC window registers */
	cr_write(sd, cr_bl[sd->cr_bl->val], ARRAY_SIZE(cr_bl[0]));
}

static void cr_set_sharpness(struct sd *sd)
{
	if (sd->cr_sharp_auto->val) {
		cr_write(sd, cr_sharp_auto_on, ARRAY_SIZE(cr_sharp_auto_on));
	} else {
		cr_write(sd, cr_sharp_auto_off, ARRAY_SIZE(cr_sharp_auto_off));
		cr_write(sd, cr_sharp[sd->cr_sharp->val], ARRAY_SIZE(cr_sharp[0]));
	}
}

static void cr_apply_extras(struct sd *sd)
{
	cr_write(sd, cr_sat[sd->cr_sat->val], ARRAY_SIZE(cr_sat[0]));
	cr_set_sharpness(sd);
	cr_write(sd, cr_gamma[sd->cr_gamma->val], ARRAY_SIZE(cr_gamma[0]));
	cr_write(sd, cr_wb[cr_wb_preset(sd->cr_wb->val)], ARRAY_SIZE(cr_wb[0]));
	cr_set_exposure(sd);
}

/* Switch sensor tuning while streaming */
static void cr_switch_tuning(struct sd *sd, bool on)
{
	struct gspca_dev *gspca_dev = &sd->gspca_dev;
	int i;

	if (on) {
		for (i = 0; i < ARRAY_SIZE(cr_init); i++)
			if (!cr_live_skip(cr_init[i].reg))
				i2c_w_mask(sd, cr_init[i].reg, cr_init[i].val,
					   cr_init[i].mask);
	} else {
		for (i = 0; i < ARRAY_SIZE(norm_7670); i++)
			if (!cr_live_skip(norm_7670[i].reg))
				i2c_w(sd, norm_7670[i].reg, norm_7670[i].val);
	}
	/* same as mode_init_ov_sensor_regs() does at stream start */
	i2c_w_mask(sd, 0x13, 0x00, 0x20);
	i2c_w_mask(sd, OV7670_R13_COM8, OV7670_COM8_AWB, OV7670_COM8_AWB);

	/* re-apply the stock controls on top */
	setbrightness(gspca_dev, sd->brightness->val);
	setcontrast(gspca_dev, sd->cr_contrast->val);
	setfreq(gspca_dev, sd->freq->val);
	sethvflip(gspca_dev, sd->hflip->val, sd->vflip->val);
	if (on)
		cr_apply_extras(sd);
}

static int cr_s_ctrl(struct v4l2_ctrl *ctrl)
{
	struct gspca_dev *gspca_dev =
		container_of(ctrl->handler, struct gspca_dev, ctrl_handler);
	struct sd *sd = (struct sd *)gspca_dev;
	bool on = sd->cr_tuning->val;
	int v;

	gspca_dev->usb_err = 0;
	if (!gspca_dev->streaming)
		return 0;

	switch (ctrl->id) {
	case CR_CID_TUNING:
		/* at stream start the probe-time table is already in place */
		if (sd->cr_tuning_applied != on)
			cr_switch_tuning(sd, on);
		sd->cr_tuning_applied = on;
		break;
	case V4L2_CID_SATURATION:
		if (on)
			cr_write(sd, cr_sat[ctrl->val], ARRAY_SIZE(cr_sat[0]));
		break;
	case CR_CID_SHARP_AUTO:
	case V4L2_CID_SHARPNESS:
		if (on)
			cr_set_sharpness(sd);
		break;
	case V4L2_CID_GAMMA:
		if (on)
			cr_write(sd, cr_gamma[ctrl->val], ARRAY_SIZE(cr_gamma[0]));
		break;
	case V4L2_CID_AUTO_N_PRESET_WHITE_BALANCE:
		if (on)
			cr_write(sd, cr_wb[cr_wb_preset(ctrl->val)],
				 ARRAY_SIZE(cr_wb[0]));
		break;
	case V4L2_CID_EXPOSURE_AUTO:
	case V4L2_CID_EXPOSURE:
	case V4L2_CID_GAIN:
	case V4L2_CID_BACKLIGHT_COMPENSATION:
		if (on)
			cr_set_exposure(sd);
		break;
	case CR_CID_REG:
	case CR_CID_VAL:
		break;		/* used by the write/read buttons */
	case CR_CID_REG_WRITE:
		i2c_w(sd, sd->cr_reg->val, sd->cr_val->val);
		break;
	case CR_CID_REG_READ:
		v = i2c_r(sd, sd->cr_reg->val);
		if (v < 0)
			return v;
		__v4l2_ctrl_s_ctrl(sd->cr_val, v);
		break;
	}
	return gspca_dev->usb_err;
}

static const struct v4l2_ctrl_ops cr_ctrl_ops = {
	.s_ctrl = cr_s_ctrl,
};

static struct v4l2_ctrl *cr_custom(struct v4l2_ctrl_handler *hdl, u32 id,
				   const char *name, enum v4l2_ctrl_type type,
				   s64 min, s64 max, s64 def)
{
	struct v4l2_ctrl_config c = {
		.ops = &cr_ctrl_ops,
		.id = id,
		.name = name,
		.type = type,
		.min = min,
		.max = max,
		.step = type == V4L2_CTRL_TYPE_BUTTON ? 0 : 1,
		.def = def,
	};

	return v4l2_ctrl_new_custom(hdl, &c, NULL);
}

/*
 * Called from sd_init_controls() for the OV7670 only. Order matters:
 * v4l2_ctrl_handler_setup() applies controls in creation order, and the
 * backlight control must come after exposure (they share registers).
 */
static void cr_init_controls(struct sd *sd, struct v4l2_ctrl_handler *hdl)
{
	sd->cr_contrast = v4l2_ctrl_find(hdl, V4L2_CID_CONTRAST);

	sd->cr_tuning = cr_custom(hdl, CR_CID_TUNING, "Creative Tuning",
				  V4L2_CTRL_TYPE_BOOLEAN, 0, 1, creative_tuning);
	sd->cr_sat = v4l2_ctrl_new_std(hdl, &cr_ctrl_ops, V4L2_CID_SATURATION,
				       0, 6, 1, CR_SAT_DEF);
	sd->cr_sharp_auto = cr_custom(hdl, CR_CID_SHARP_AUTO, "Sharpness, Auto",
				      V4L2_CTRL_TYPE_BOOLEAN, 0, 1, 1);
	sd->cr_sharp = v4l2_ctrl_new_std(hdl, &cr_ctrl_ops, V4L2_CID_SHARPNESS,
					 0, 9, 1, CR_SHARP_DEF);
	sd->cr_gamma = v4l2_ctrl_new_std(hdl, &cr_ctrl_ops, V4L2_CID_GAMMA,
					 0, 4, 1, CR_GAMMA_DEF);
	sd->cr_wb = v4l2_ctrl_new_std_menu(hdl, &cr_ctrl_ops,
		V4L2_CID_AUTO_N_PRESET_WHITE_BALANCE,
		V4L2_WHITE_BALANCE_DAYLIGHT,
		~(BIT(V4L2_WHITE_BALANCE_AUTO) |
		  BIT(V4L2_WHITE_BALANCE_INCANDESCENT) |
		  BIT(V4L2_WHITE_BALANCE_FLUORESCENT) |
		  BIT(V4L2_WHITE_BALANCE_DAYLIGHT)),
		V4L2_WHITE_BALANCE_AUTO);
	sd->cr_exp_auto = v4l2_ctrl_new_std_menu(hdl, &cr_ctrl_ops,
		V4L2_CID_EXPOSURE_AUTO, V4L2_EXPOSURE_MANUAL,
		~(BIT(V4L2_EXPOSURE_AUTO) | BIT(V4L2_EXPOSURE_MANUAL)),
		V4L2_EXPOSURE_AUTO);
	sd->cr_exp = v4l2_ctrl_new_std(hdl, &cr_ctrl_ops, V4L2_CID_EXPOSURE,
				       0, 15, 1, CR_EXP_DEF);
	sd->cr_gain = v4l2_ctrl_new_std(hdl, &cr_ctrl_ops, V4L2_CID_GAIN,
					0, 7, 1, CR_GAIN_DEF);
	sd->cr_bl = v4l2_ctrl_new_std(hdl, &cr_ctrl_ops,
				      V4L2_CID_BACKLIGHT_COMPENSATION,
				      0, 1, 1, CR_BL_DEF);

	/* raw sensor register access, for experiments */
	sd->cr_reg = cr_custom(hdl, CR_CID_REG, "Sensor Register",
			       V4L2_CTRL_TYPE_INTEGER, 0, 255, 0);
	sd->cr_val = cr_custom(hdl, CR_CID_VAL, "Sensor Value",
			       V4L2_CTRL_TYPE_INTEGER, 0, 255, 0);
	cr_custom(hdl, CR_CID_REG_WRITE, "Write Sensor Register",
		  V4L2_CTRL_TYPE_BUTTON, 0, 0, 0);
	cr_custom(hdl, CR_CID_REG_READ, "Read Sensor Register",
		  V4L2_CTRL_TYPE_BUTTON, 0, 0, 0);
}

/* Frame rate via VIDIOC_G/S_PARM, applied at the next stream start */
static void cr_get_streamparm(struct gspca_dev *gspca_dev,
			      struct v4l2_streamparm *parm)
{
	struct sd *sd = (struct sd *)gspca_dev;
	struct v4l2_fract *tpf = &parm->parm.capture.timeperframe;

	tpf->numerator = 1;
	tpf->denominator = sd->frame_rate ? sd->frame_rate : 15;
}

static void cr_set_streamparm(struct gspca_dev *gspca_dev,
			      struct v4l2_streamparm *parm)
{
	struct sd *sd = (struct sd *)gspca_dev;
	struct v4l2_fract *tpf = &parm->parm.capture.timeperframe;
	static const u8 rates[] = { 30, 20, 15 };	/* what ov519_mode_init_regs() knows */
	int fps, i;

	if (sd->sensor == SEN_OV7670 && tpf->numerator && tpf->denominator) {
		fps = tpf->denominator / tpf->numerator;
		for (i = 0; i < ARRAY_SIZE(rates) - 1; i++)
			if (fps >= rates[i])
				break;
		sd->frame_rate = rates[i];
	}
	cr_get_streamparm(gspca_dev, parm);
}
