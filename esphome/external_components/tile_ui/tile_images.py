"""Image variant computation and image/icon lambda generation helpers."""
import copy
import json

from .tile_utils import build_fast_refresh_lambda, build_expression

# ---------------------------------------------------------------------------
# Per-page-size image variant helpers
# ---------------------------------------------------------------------------

def is_image_param_type(param_type) -> bool:
    """Return True if *param_type* represents an ESPHome Image pointer parameter."""
    if not param_type:
        return False
    t = str(param_type).strip()
    return t == 'image' or t == 'esphome::image::Image*'


def normalize_image_param_id(val) -> str:
    """Extract a bare image ID from a script parameter value (stripping id()/&id())."""
    if not isinstance(val, str):
        return ""
    s = val.strip()
    if s.startswith("&id(") and s.endswith(")"):
        s = s[4:-1].strip()
    elif s.startswith("id(") and s.endswith(")"):
        s = s[3:-1].strip()
    return s


def _get_script_params(available_scripts: dict | None, script_id: str) -> dict:
    if not available_scripts:
        return {}
    info = available_scripts.get(script_id)
    if info is None:
        for key, val in available_scripts.items():
            if str(key) == str(script_id):
                info = val
                break
    return info.get('parameters', {}) if isinstance(info, dict) else {}


def _variant_key(img_id: str, rows: int, cols: int, x_span: int = 1, y_span: int = 1) -> tuple:
    if x_span == 1 and y_span == 1:
        return (img_id, rows, cols)
    return (img_id, rows, cols, x_span, y_span)


def compute_image_variants(screens: list, available_scripts: dict | None = None) -> dict:
    """
    Scan screens and return a mapping ``(img_id, rows, cols[, x_span, y_span]) -> variant_id``.

    * When an image appears in only one tile size (rows×cols×x_span×y_span), the
      variant_id is kept as the original image ID (no suffix).
    * When the same image appears in multiple tile sizes a unique suffix
      ``_r{rows}c{cols}`` (plus ``_s{x_span}x{y_span}`` for spanned tiles) is
      appended so that ESPHome can declare separate, correctly-sized image
      objects for each tile size.
    """
    img_sizes: dict = {}  # img_id -> set of (rows, cols, x_span, y_span)
    for screen in screens:
        rows = screen.get('rows', 2)
        cols = screen.get('cols', 2)
        for tile_obj in screen.get('tiles', []):
            if not isinstance(tile_obj, dict):
                continue
            for _tname, tdata in tile_obj.items():
                if not isinstance(tdata, dict):
                    continue
                x_span = max(1, int(tdata.get('x_span', 1) or 1))
                y_span = max(1, int(tdata.get('y_span', 1) or 1))
                size_key = (rows, cols, x_span, y_span)
                for entry in (tdata.get('display_assets') or []):
                    if isinstance(entry, dict):
                        if entry.get('image') and entry['image'] != 'none':
                            img_sizes.setdefault(entry['image'], set()).add(size_key)
                        # Track per-step image overrides
                        anim = entry.get('animation')
                        if isinstance(anim, dict) and isinstance(anim.get('steps'), list):
                            for step in anim['steps']:
                                if isinstance(step, dict) and step.get('image') and step['image'] != 'none':
                                    img_sizes.setdefault(step['image'], set()).add(size_key)
                if available_scripts:
                    display_list = tdata.get('display')
                    if isinstance(display_list, list):
                        for item in display_list:
                            if not isinstance(item, dict):
                                continue
                            for script_id, params in item.items():
                                if not isinstance(params, dict):
                                    continue
                                script_params = _get_script_params(available_scripts, script_id)
                                for param_name, param_val in params.items():
                                    if is_image_param_type(script_params.get(param_name)):
                                        img_id = normalize_image_param_id(param_val)
                                        if img_id and img_id not in ('none', 'nullptr'):
                                            img_sizes.setdefault(img_id, set()).add(size_key)

    variant_id: dict = {}  # (img_id, rows, cols[, x_span, y_span]) -> variant_id
    for iid, sizes in img_sizes.items():
        sorted_sizes = sorted(sizes)
        if len(sorted_sizes) == 1:
            r, c, xs, ys = sorted_sizes[0]
            variant_id[_variant_key(iid, r, c, xs, ys)] = iid
        else:
            for (r, c, xs, ys) in sorted_sizes:
                suffix = f"_r{r}c{c}" if (xs == 1 and ys == 1) else f"_r{r}c{c}_s{xs}x{ys}"
                variant_id[_variant_key(iid, r, c, xs, ys)] = f"{iid}{suffix}"

    return variant_id


def apply_image_variants(screens: list, variant_id: dict, available_scripts: dict | None = None) -> list:
    """
    Return a deep copy of ``screens`` where every tile’s image references
    have been replaced with their per-layout/per-span variant IDs.
    """
    result = copy.deepcopy(screens)
    for screen in result:
        rows = screen.get('rows', 2)
        cols = screen.get('cols', 2)
        for tile_obj in screen.get('tiles', []):
            if not isinstance(tile_obj, dict):
                continue
            for _tname, tdata in tile_obj.items():
                if not isinstance(tdata, dict):
                    continue
                x_span = max(1, int(tdata.get('x_span', 1) or 1))
                y_span = max(1, int(tdata.get('y_span', 1) or 1))
                timages = tdata.get('display_assets')
                if isinstance(timages, list):
                    new_entries = []
                    for e in timages:
                        if not isinstance(e, dict):
                            new_entries.append(e)
                            continue
                        ne = dict(e)
                        if ne.get('image') and ne['image'] != 'none':
                            ne['image'] = variant_id.get(_variant_key(ne['image'], rows, cols, x_span, y_span), ne['image'])
                        # Substitute per-step image overrides
                        anim = ne.get('animation')
                        if isinstance(anim, dict) and isinstance(anim.get('steps'), list):
                            new_steps = []
                            for step in anim['steps']:
                                s = dict(step)
                                if s.get('image') and s['image'] != 'none':
                                    s['image'] = variant_id.get(_variant_key(s['image'], rows, cols, x_span, y_span), s['image'])
                                new_steps.append(s)
                            ne['animation'] = {**anim, 'steps': new_steps}
                        new_entries.append(ne)
                    tdata['display_assets'] = new_entries
                if available_scripts and isinstance(tdata.get('display'), list):
                    new_display = []
                    for item in tdata['display']:
                        if not isinstance(item, dict):
                            new_display.append(item)
                            continue
                        new_item = {}
                        for script_id, params in item.items():
                            if not isinstance(params, dict):
                                new_item[script_id] = params
                                continue
                            script_params = _get_script_params(available_scripts, script_id)
                            new_params = dict(params)
                            for param_name, param_val in params.items():
                                if is_image_param_type(script_params.get(param_name)):
                                    img_id = normalize_image_param_id(param_val)
                                    if img_id and img_id not in ('none', 'nullptr'):
                                        new_params[param_name] = variant_id.get(_variant_key(img_id, rows, cols, x_span, y_span), img_id)
                            new_item[script_id] = new_params
                        new_display.append(new_item)
                    tdata['display'] = new_display
    return result

# ---------------------------------------------------------------------------
# Image lambda helpers
# ---------------------------------------------------------------------------

_CPP_TYPE_MAP = {
    'int': 'int',
    'float': 'float',
    'bool': 'bool',
    'string': 'std::string',
    'string[]': 'std::vector<std::string>',
}


def _cpp_param_type(p_type: str) -> str:
    return _CPP_TYPE_MAP.get(p_type, 'auto')


def _build_lambda_sig(expected_params) -> str:
    """Build a C++ lambda parameter list string from expected_params."""
    args = []
    for i, (_, p_type) in enumerate(expected_params):
        args.append(f"{_cpp_param_type(p_type)} arg{i}")
    return ", ".join(args)


def _get_animation_fast_refresh(config: dict):
    """
    Derive a requires_fast_refresh value from animation settings in the display_assets list.

    Returns:
      None – no animation entries
      True – at least one animation entry (always fast-refresh)
    """
    images = config.get("display_assets")
    if not images or not isinstance(images, list):
        return None

    has_animation = False

    for entry in images:
        if not isinstance(entry, dict):
            continue
        animation = entry.get("animation")
        if animation and isinstance(animation, dict):
            has_animation = True
            break

    return True if has_animation else None


def _build_image_lambda(config: dict, expected_params: list) -> str | None:
    """
    Return a C++ expression for use as a single draw-funcs list entry.

    For a single, unconditional, single-step entry this is a bare
    ``make_image_draw(...)`` call; the caller wraps it in ``{ }`` to form a
    valid DrawImageFunc initialiser list.

    For multi-step or conditional entries a lambda is returned instead.

    animation formats supported:
      Single-step (legacy):  { direction, duration }
      Multi-step:            { steps: [{ direction, duration }   <- step 0
                                       { direction, duration }   <- steps 1+
                                       ...] }
    Each step draws the entry's root image (or step-level icon override).
    Use multiple steps instead of image cycling within a single step.

    Each entry in 'display_assets':
      { image: <id>, condition?: <expr>, animation?: <above> }
    """
    images = config.get("display_assets")
    if not images or not isinstance(images, list):
        legacy_image = config.get("image")
        if legacy_image:
            images = [{"image": legacy_image}]
        else:
            return None

    valid_entries = [e for e in images if isinstance(e, dict) and (e.get("image") or e.get("icon"))]
    if not valid_entries:
        return None

    sig = _build_lambda_sig(expected_params)
    param_types = [p_type for (_, p_type) in expected_params]

    has_vec = 'string[]' in param_types
    if has_vec:
        vec_idx = param_types.index('string[]')
        entities_binding = f"  const std::vector<std::string>& entities = arg{vec_idx};"
        draw_entities = f"arg{vec_idx}"
    else:
        entities_binding = "  const std::vector<std::string> entities{};"
        draw_entities = "{}"
    args_cpp = f"arg0, arg1, arg2, arg3, {draw_entities}"
    direct_draw_signature = param_types == ['int', 'int', 'int', 'int', 'string[]']

    # Legacy direction → (from_x, from_y, to_x, to_y) fracs.
    _LEGACY_DIR_POS = {
        'left_right': (0.0, 0.5, 1.0, 0.5),
        'right_left': (1.0, 0.5, 0.0, 0.5),
        'up_down':    (0.5, 0.0, 0.5, 1.0),
        'down_up':    (0.5, 1.0, 0.5, 0.0),
    }

    def _step_positions(step: dict):
        """Return (from_x, from_y, to_x, to_y) fracs, or None for static (no motion)."""
        if 'direction' in step:
            d = step['direction']
            if d == 'none':
                return None
            return _LEGACY_DIR_POS.get(d)

        def _resolve_pos(pos) -> tuple:
            """Convert an [x, y] position list to (x_frac, y_frac)."""
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                return (float(pos[0]), float(pos[1]))
            return (0.5, 0.5)  # fallback to center

        from_pos = step.get('from', [0.5, 0.5])
        to_pos   = step.get('to',   [0.5, 0.5])
        fx, fy = _resolve_pos(from_pos)
        tx, ty = _resolve_pos(to_pos)
        # Both fracs at center (0.5, 0.5) → static overload (no position args)
        if fx == 0.5 and fy == 0.5 and tx == 0.5 and ty == 0.5:
            return None
        return (fx, fy, tx, ty)

    # -----------------------------------------------------------------------
    # Icon formatting helpers
    # -----------------------------------------------------------------------

    def _icon_to_cpp(icon_val) -> str:
        """Convert icon value from YAML to a C++ string literal."""
        if not isinstance(icon_val, str):
            return '""'
        val = icon_val
        # Already a 1-char decoded Unicode (Python YAML may have interpreted \U...)
        if len(val) == 1 and ord(val) > 127:
            utf8 = val.encode('utf-8')
            return '"' + ''.join(f'\\x{b:02x}' for b in utf8) + '"'
        # Wrapped in double quotes (standard YAML generator output, e.g. '"\U0000F05A"')
        if val.startswith('"') and val.endswith('"') and len(val) >= 2:
            return val  # already C++ formatted
        # Raw backslash-U notation (unlikely but handle it)
        return f'"{val}"'

    def _icon_color_cpp(val: str) -> str:
        """Format icon_color as a C++ Color expression."""
        if not val:
            return 'id(white)'
        if val.startswith('Color(') or val.startswith('id('):
            return val
        return f'id({val})'

    def _icon_size_cpp(val: str) -> str:
        """Format icon_size as a C++ BaseFont* expression."""
        if not val:
            return '&id(big)'
        if val.startswith('&id('):
            return val
        if val.startswith('id('):
            return f'&{val}'
        return f'&id({val})'

    def _make_icon_draw_call_step(step: dict, icon_cpp: str, color_cpp: str, font_cpp: str,
                                   total_ms: int = None, step_start_ms: int = None) -> str:
        """Return a make_icon_draw(...) expression for one animation step."""
        positions = _step_positions(step)
        duration_ms = int(float(step.get("duration", 3)) * 1000)
        if positions is None:
            if total_ms is not None:
                # static within a multi-step — use the step-aligned static overload
                return f"make_icon_draw({icon_cpp}, {color_cpp}, {font_cpp})"
            return f"make_icon_draw({icon_cpp}, {color_cpp}, {font_cpp})"
        fx, fy, tx, ty = positions
        pos_args = f"{fx:.1f}f, {fy:.1f}f, {tx:.1f}f, {ty:.1f}f"
        if total_ms is not None:
            return f"make_icon_draw({icon_cpp}, {color_cpp}, {font_cpp}, {pos_args}, {duration_ms}U, {total_ms}U, {step_start_ms}U)"
        return f"make_icon_draw({icon_cpp}, {color_cpp}, {font_cpp}, {pos_args}, {duration_ms}U)"

    def _make_draw_call_step(step: dict, img_id: str,
                              total_ms: int = None, step_start_ms: int = None) -> str | None:
        """Return a make_image_draw(...) expression for one animation step, or None for no-op."""
        positions = _step_positions(step)
        duration_ms = int(float(step.get("duration", 3)) * 1000)
        aligned = total_ms is not None
        if positions is None:
            return f"make_image_draw(&id({img_id}))"
        fx, fy, tx, ty = positions
        pos_args = f"{fx:.1f}f, {fy:.1f}f, {tx:.1f}f, {ty:.1f}f"
        if aligned:
            return f"make_image_draw(&id({img_id}), {pos_args}, {duration_ms}U, {total_ms}U, {step_start_ms}U)"
        return f"make_image_draw(&id({img_id}), {pos_args}, {duration_ms}U)"

    def _get_steps(entry: dict) -> list:
        """Return the list of animation steps (always at least 1 element if animated)."""
        animation = entry.get("animation") if isinstance(entry, dict) else None
        if not animation or not isinstance(animation, dict):
            return []
        steps = animation.get("steps")
        if steps and isinstance(steps, list) and len(steps) > 0:
            return steps
        return [animation]  # single-step: treat the animation dict itself as the one step

    def _make_draw_call(entry: dict) -> str | None:
        """Bare draw call expression using the first (or only) step, or None for no-op."""
        steps = _get_steps(entry)
        step0 = steps[0] if steps else None
        # Check per-step icon override on step 0 first
        if step0 is not None and step0.get("icon") is not None:
            sc = _icon_to_cpp(step0["icon"])
            scolor = _icon_color_cpp(step0.get("icon_color", ""))
            sfont = _icon_size_cpp(step0.get("icon_size", ""))
            return _make_icon_draw_call_step(step0, sc, scolor, sfont)
        if entry.get("icon"):
            icon_cpp = _icon_to_cpp(entry["icon"])
            color_cpp = _icon_color_cpp(entry.get("icon_color", ""))
            font_cpp = _icon_size_cpp(entry.get("icon_size", ""))
            if not steps:
                return f"make_icon_draw({icon_cpp}, {color_cpp}, {font_cpp})"
            return _make_icon_draw_call_step(steps[0], icon_cpp, color_cpp, font_cpp)
        img_id = entry["image"]
        if not steps:
            return f"make_image_draw(&id({img_id}))"
        return _make_draw_call_step(steps[0], img_id)

    def _entry_dispatch_lines(entry: dict) -> list[str]:
        """
        C++ statement lines that perform the full draw for this entry.
        Single-step entries produce one line; multi-step produce a time-dispatch block.
        Each step may override the entry-level image/icon with its own 'icon' key.
        """
        steps = _get_steps(entry)
        is_icon_entry = bool(entry.get("icon") and entry["icon"].strip())

        def _draw_call_for_step(step: dict, step_idx: int,
                                total_ms: int = None, step_start_ms: int = None) -> str | None:
            """Return draw call for a specific step.
            Priority: per-step icon > per-step image > entry-level icon > entry-level image.
            """
            step_icon = step.get("icon")
            step_image = step.get("image")
            if step_icon is not None and step_icon.strip():
                # Per-step icon override
                sc = _icon_to_cpp(step_icon)
                scolor = _icon_color_cpp(step.get("icon_color", ""))
                sfont = _icon_size_cpp(step.get("icon_size", ""))
                return _make_icon_draw_call_step(step, sc, scolor, sfont, total_ms, step_start_ms)
            elif step_image and step_image.strip():
                # Per-step image override (takes priority over entry-level icon)
                return _make_draw_call_step(step, step_image, total_ms, step_start_ms)
            elif is_icon_entry:
                # Fall back to entry-level icon
                ic = _icon_to_cpp(entry["icon"])
                icolor = _icon_color_cpp(entry.get("icon_color", ""))
                ifont = _icon_size_cpp(entry.get("icon_size", ""))
                return _make_icon_draw_call_step(step, ic, icolor, ifont, total_ms, step_start_ms)
            else:
                # Image entry: use entry-level image
                return _make_draw_call_step(step, entry["image"], total_ms, step_start_ms)

        if len(steps) <= 1:
            call = _make_draw_call(entry)
            if call is None:
                return []
            return [f"{call}({args_cpp});"]
        total_ms = sum(int(float(s.get("duration", 3)) * 1000) for s in steps)
        lines: list[str] = [f"uint32_t _t = millis() % {total_ms}U;"]
        cumulative = 0
        kw = "if"
        for i, step in enumerate(steps):
            step_start = cumulative
            cumulative += int(float(step.get("duration", 3)) * 1000)
            call = _draw_call_for_step(step, i, total_ms, step_start)
            if i == len(steps) - 1:
                lines.append("else")
            else:
                lines.append(f"{kw} (_t < {cumulative}U)")
                kw = "else if"
            if call is None:
                lines.append("  ; /* none */")
            else:
                lines.append(f"  {call}({args_cpp});")
        return lines

    # Normalize 'none' sentinel to the built-in transparent image so it draws
    # a 1×1 transparent pixel (effectively invisible) instead of crashing.
    def _norm_img(img_id: str) -> str:
        return 'none_transparent' if img_id == 'none' else img_id

    def _normalize_entry(e: dict) -> dict:
        e = dict(e)
        # Icon entries don't use image IDs — skip image normalization
        if not e.get("icon") and 'image' in e:
            e['image'] = _norm_img(e['image'])
        return e

    valid_entries = [_normalize_entry(e) for e in valid_entries]
    has_any_condition = any(e.get("condition") for e in valid_entries)

    # -----------------------------------------------------------------------
    # Simple path: single entry, no conditions.
    # -----------------------------------------------------------------------
    if not has_any_condition and len(valid_entries) == 1:
        entry = valid_entries[0]
        if len(_get_steps(entry)) <= 1:
            call = _make_draw_call(entry)
            if call is None:
                return []
            if not direct_draw_signature:
                return [f"[draw = {call}]({sig}) {{ draw({args_cpp}); }}"]
            return [call]  # bare expr; caller wraps in { }
        # Multi-step requires a lambda so the time dispatch runs each call
        body = "\n".join(f"  {l}" for l in _entry_dispatch_lines(entry))
        return [f"[=]({sig}) {{\n{body}\n}}"]

    # -----------------------------------------------------------------------
    # All-layers path: one lambda per entry.
    # ALL entries whose conditions are true are rendered (bottom to top).
    # -----------------------------------------------------------------------
    results: list[str] = []
    for entry in valid_entries:
        cond_expr = entry.get("condition")
        dispatch = _entry_dispatch_lines(entry)
        body_lines = [entities_binding]
        if cond_expr:
            expr = build_expression(cond_expr)
            if not expr:
                continue
            if len(dispatch) == 1:
                body_lines += [f"  if ({expr})", f"    {dispatch[0]}"]
            else:
                body_lines.append(f"  if ({expr}) {{")
                body_lines += [f"    {l}" for l in dispatch]
                body_lines.append("  }")
        else:
            body_lines += [f"  {l}" for l in dispatch]
        results.append(f"[=]({sig}) {{\n" + "\n".join(filter(None, body_lines)) + "\n}")

    return results or []


def _override_display_with_image(display_cpp: str, config: dict, expected_params: list) -> str:
    """
    If config has 'image' or 'display_assets', replace the display list with one
    DrawImageFunc per display_assets entry.  All entries whose conditions are true
    are rendered in order (first = bottom layer, last = top layer).
    Returns the original display_cpp unchanged if no images are configured.
    """
    lams = _build_image_lambda(config, expected_params)
    if lams is None:
        return display_cpp
    return "{ " + ", ".join(lams) + " }"


# Keep old name as alias so any external callers aren't broken
_append_image_lambda = _override_display_with_image


