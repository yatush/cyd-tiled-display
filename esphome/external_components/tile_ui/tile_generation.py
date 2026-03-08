"""Tile generation functions - converts YAML tile configs to C++ code."""
import copy
from typing import Any

from .tile_utils import (
    format_display_list, format_functions_list, format_entity_value,
    build_fast_refresh_lambda, build_expression, format_entity_cpp, get_tile_modifiers,
    flags_to_cpp, format_single_function
)
from .schema import TileType

__all__ = [
    "generate_tile_cpp",
    "generate_action_tile",
    "generate_title_tile",
    "generate_move_page_tile",
    "generate_function_tile",
    "generate_toggle_entity_tile",
    "generate_cycle_entity_tile",
    "compute_image_variants",
    "apply_image_variants",
]

# ---------------------------------------------------------------------------
# Per-page-size image variant helpers
# ---------------------------------------------------------------------------

def compute_image_variants(screens: list) -> dict:
    """
    Scan screens and return a mapping ``(img_id, rows, cols) -> variant_id``.

    * When an image appears in only one page layout (rows×cols), the
      variant_id is kept as the original image ID (no suffix).
    * When the same image appears in multiple layouts a unique suffix
      ``_r{rows}c{cols}`` is appended so that ESPHome can declare
      separate, correctly-sized image objects for each layout.
    """
    img_sizes: dict = {}  # img_id -> set of (rows, cols)
    for screen in screens:
        rows = screen.get('rows', 2)
        cols = screen.get('cols', 2)
        for tile_obj in screen.get('tiles', []):
            if not isinstance(tile_obj, dict):
                continue
            for _tname, tdata in tile_obj.items():
                if not isinstance(tdata, dict):
                    continue
                for entry in (tdata.get('images') or []):
                    if isinstance(entry, dict):
                        if entry.get('image') and entry['image'] != 'none':
                            img_sizes.setdefault(entry['image'], set()).add((rows, cols))
                        anim = entry.get('animation')
                        if isinstance(anim, dict):
                            steps = anim.get('steps')
                            if steps and isinstance(steps, list):
                                for i, step in enumerate(steps):
                                    key = 'extra_images' if i == 0 else 'images'
                                    for img in (step.get(key) or []):
                                        if img and img != 'none':
                                            img_sizes.setdefault(img, set()).add((rows, cols))
                            else:
                                for extra in (anim.get('extra_images') or []):
                                    if extra and extra != 'none':
                                        img_sizes.setdefault(extra, set()).add((rows, cols))

    variant_id: dict = {}  # (img_id, rows, cols) -> variant_id
    for iid, sizes in img_sizes.items():
        sorted_sizes = sorted(sizes)
        if len(sorted_sizes) == 1:
            r, c = sorted_sizes[0]
            variant_id[(iid, r, c)] = iid
        else:
            for (r, c) in sorted_sizes:
                variant_id[(iid, r, c)] = f"{iid}_r{r}c{c}"

    return variant_id


def apply_image_variants(screens: list, variant_id: dict) -> list:
    """
    Return a deep copy of ``screens`` where every tile’s image references
    have been replaced with their per-layout variant IDs.
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
                timages = tdata.get('images')
                if isinstance(timages, list):
                    new_entries = []
                    for e in timages:
                        if not isinstance(e, dict):
                            new_entries.append(e)
                            continue
                        ne = dict(e)
                        if ne.get('image') and ne['image'] != 'none':
                            ne['image'] = variant_id.get((ne['image'], rows, cols), ne['image'])
                        anim = ne.get('animation')
                        if isinstance(anim, dict):
                            steps = anim.get('steps')
                            if steps and isinstance(steps, list):
                                new_steps = []
                                for i, step in enumerate(steps):
                                    key = 'extra_images' if i == 0 else 'images'
                                    imgs = step.get(key)
                                    if imgs:
                                        new_steps.append({**step, key: [
                                            variant_id.get((img, rows, cols), img)
                                            if isinstance(img, str) and img != 'none' else img
                                            for img in imgs
                                        ]})
                                    else:
                                        new_steps.append(step)
                                ne['animation'] = {**anim, 'steps': new_steps}
                            elif anim.get('extra_images'):
                                ne['animation'] = {
                                    **anim,
                                    'extra_images': [
                                        variant_id.get((img, rows, cols), img)
                                        if isinstance(img, str) and img != 'none' else img
                                        for img in anim['extra_images']
                                    ],
                                }
                        new_entries.append(ne)
                    tdata['images'] = new_entries
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
    Derive a requires_fast_refresh value from animation settings in the images list.

    Returns:
      None – no animation entries
      True – at least one animation entry (always fast-refresh)
    """
    images = config.get("images")
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
      Single-step (legacy):  { direction, duration, extra_images? }
      Multi-step:            { steps: [{ direction, duration, extra_images? }   <- step 0
                                       { direction, duration, images? }          <- steps 1+
                                       ...] }
    For step 0: root image + extra_images are cycled together.
    For steps 1+: 'images' list is used standalone; if omitted, root image is used alone.

    Each entry in 'images':
      { image: <id>, condition?: <expr>, animation?: <above> }
    """
    images = config.get("images")
    if not images or not isinstance(images, list):
        legacy_image = config.get("image")
        if legacy_image:
            images = [{"image": legacy_image}]
        else:
            return None

    valid_entries = [e for e in images if isinstance(e, dict) and e.get("image")]
    if not valid_entries:
        return None

    sig = _build_lambda_sig(expected_params)
    n_params = len(expected_params)
    args_cpp = ", ".join(f"arg{i}" for i in range(n_params))
    param_types = [p_type for (_, p_type) in expected_params]

    has_vec = 'string[]' in param_types
    if has_vec:
        vec_idx = param_types.index('string[]')
        entities_binding = f"  const std::vector<std::string>& entities = arg{vec_idx};"
    else:
        entities_binding = "  const std::vector<std::string> entities{};"

    # Position → (x_frac, y_frac) within the tile.
    # x_frac: left=0.0, middle=0.5, right=1.0
    # y_frac: top=0.0,  center=0.5, bottom=1.0
    _POS_X_FRAC = {'left': 0.0, 'middle': 0.5, 'right': 1.0}
    _POS_Y_FRAC = {'top': 0.0, 'center': 0.5, 'bottom': 1.0}

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

        def _resolve_pos(pos, default='center_middle'):
            """Convert a position (named string or [x,y] list) to (x_frac, y_frac)."""
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                return (float(pos[0]), float(pos[1]))
            # Named string
            p = pos if isinstance(pos, str) else default
            return (_POS_X_FRAC[p.split('_', 1)[1]], _POS_Y_FRAC[p.split('_')[0]])

        from_pos = step.get('from', 'center_middle')
        to_pos   = step.get('to',   'center_middle')
        fx, fy = _resolve_pos(from_pos)
        tx, ty = _resolve_pos(to_pos)
        # Both fracs at center (0.5, 0.5) → use default static overload (no position args)
        if fx == 0.5 and fy == 0.5 and tx == 0.5 and ty == 0.5:
            return None
        return (fx, fy, tx, ty)

    def _make_draw_call_step(step: dict, root_img_id: str, is_first: bool,
                              total_ms: int = None, step_start_ms: int = None) -> str | None:
        """Return a make_image_draw(...) expression for one animation step, or None for no-op."""
        positions = _step_positions(step)
        duration_ms = int(float(step.get("duration", 3)) * 1000)
        if is_first:
            extra = [img for img in (step.get("extra_images") or []) if img]
            all_images = [root_img_id] + extra
        else:
            imgs = [img for img in (step.get("images") or []) if img]
            all_images = imgs if imgs else [root_img_id]
        if not all_images:
            return None
        n = len(all_images)
        aligned = total_ms is not None
        if n > 1:
            imgs_cpp = "{" + ", ".join(f"&id({img})" for img in all_images) + "}"
            if positions is None:
                if aligned:
                    return f"make_image_draw({imgs_cpp}, {duration_ms}U, {total_ms}U, {step_start_ms}U)"
                return f"make_image_draw({imgs_cpp}, {duration_ms}U)"
            fx, fy, tx, ty = positions
            pos_args = f"{fx:.1f}f, {fy:.1f}f, {tx:.1f}f, {ty:.1f}f"
            if aligned:
                return f"make_image_draw({imgs_cpp}, {pos_args}, {duration_ms}U, {total_ms}U, {step_start_ms}U)"
            return f"make_image_draw({imgs_cpp}, {pos_args}, {duration_ms}U)"
        img = all_images[0]
        if positions is None:
            return f"make_image_draw(&id({img}))"
        fx, fy, tx, ty = positions
        pos_args = f"{fx:.1f}f, {fy:.1f}f, {tx:.1f}f, {ty:.1f}f"
        if aligned:
            return f"make_image_draw(&id({img}), {pos_args}, {duration_ms}U, {total_ms}U, {step_start_ms}U)"
        return f"make_image_draw(&id({img}), {pos_args}, {duration_ms}U)"

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
        """Bare make_image_draw(...) expression using the first (or only) step, or None for no-op."""
        img_id = entry["image"]
        steps = _get_steps(entry)
        if not steps:
            return f"make_image_draw(&id({img_id}))"
        return _make_draw_call_step(steps[0], img_id, True)

    def _entry_dispatch_lines(entry: dict) -> list[str]:
        """
        C++ statement lines that perform the full draw for this entry.
        Single-step entries produce one line; multi-step produce a time-dispatch block.
        """
        img_id = entry["image"]
        steps = _get_steps(entry)
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
            call = _make_draw_call_step(step, img_id, i == 0, total_ms, step_start)
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
        if 'image' in e:
            e['image'] = _norm_img(e['image'])
        anim = e.get('animation')
        if isinstance(anim, dict):
            anim = dict(anim)
            steps = anim.get('steps')
            if steps and isinstance(steps, list):
                new_steps = []
                for i, step in enumerate(steps):
                    step = dict(step)
                    key = 'extra_images' if i == 0 else 'images'
                    if step.get(key):
                        step[key] = [_norm_img(img) for img in step[key]]
                    new_steps.append(step)
                anim['steps'] = new_steps
            elif anim.get('extra_images'):
                anim['extra_images'] = [_norm_img(img) for img in anim['extra_images']]
            e['animation'] = anim
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
    If config has 'image' or 'images', replace the display list with one
    DrawImageFunc per images entry.  All entries whose conditions are true
    are rendered in order (first = bottom layer, last = top layer).
    Returns the original display_cpp unchanged if no images are configured.
    """
    lams = _build_image_lambda(config, expected_params)
    if lams is None:
        return display_cpp
    return "{ " + ", ".join(lams) + " }"


# Keep old name as alias so any external callers aren't broken
_append_image_lambda = _override_display_with_image


def _generate_base_tile_args(config, available_scripts, expected_display_params):
    """Extract base tile arguments (x, y, display)."""
    x = config.get("x", 0)
    y = config.get("y", 0)
    display = config.get("display", [])
    display_cpp = format_display_list(display, available_scripts, expected_display_params)
    return x, y, display_cpp


def _apply_modifiers(tile_cpp, config, extra_modifiers=None, screen_id=None):
    """Apply common modifiers to the tile C++ object."""
    method_chains = []
    if extra_modifiers:
        method_chains.extend(extra_modifiers)
        
    method_chains.extend(get_tile_modifiers(config, screen_id))
    
    if method_chains:
        tile_cpp = f'({tile_cpp})'
        for method in method_chains:
            tile_cpp += f'->{method}'
    
    return tile_cpp


def generate_action_tile(config, available_scripts, screen_id=None):
    """Generate C++ for an action tile."""
    # HAActionTile display: int, int, vector<string>
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('entities', 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    entities_config = config.get("entities", "")
    entity_values = format_entity_value(entities_config)
    perform = config.get("perform", [])
    location_perform = config.get("location_perform", [])
    display_page = config.get("display_page_if_no_entity", None)
    requires_fast_refresh = (
        config["requires_fast_refresh"] if "requires_fast_refresh" in config
        else _get_animation_fast_refresh(config)
    )
    
    if display_page:
        has_dynamic_entity = False
        if isinstance(entities_config, list):
            for entity in entities_config:
                if isinstance(entity, dict) and "dynamic_entity" in entity:
                    has_dynamic_entity = True
                    break
        elif isinstance(entities_config, dict) and "dynamic_entity" in entities_config:
            has_dynamic_entity = True
        
        if not has_dynamic_entity:
            raise ValueError(
                f"Screen '{screen_id}', Tile at ({x}, {y}): display_page_if_no_entity requires at least one dynamic_entity"
            )
    
    # HAActionTile perform: vector<string>
    perform_cpp = format_functions_list(perform, available_scripts, [('entities', 'string[]')])
    # HAActionTile location_perform: float, float, vector<string>
    location_perform_cpp = format_functions_list(location_perform, available_scripts, [('x', 'float'), ('y', 'float'), ('entities', 'string[]')])
    entity_cpp = format_entity_cpp(entity_values)
    
    args = [str(x), str(y), display_cpp]
    
    if perform and location_perform:
        args.append(perform_cpp)
        args.append(location_perform_cpp)
    elif perform:
        args.append(perform_cpp)
    elif location_perform:
        args.append("{}")
        args.append(location_perform_cpp)
    
    args.append(entity_cpp)
    
    tile_cpp = f'new HAActionTile({", ".join(args)})'
    
    modifiers = []
    # Apply specific modifiers before common ones
    if display_page:
        modifiers.append(f'setDisplayPageIfNoEntity(&id({display_page}))')
    
    x = config.get("x", "?")
    y = config.get("y", "?")
    context = f"Screen '{screen_id}', Tile at ({x}, {y})" if screen_id else f"Tile at ({x}, {y})"
    
    fast_refresh_lambda = build_fast_refresh_lambda(requires_fast_refresh, context)
    if fast_refresh_lambda:
        modifiers.append(f'setRequiresFastRefreshFunc({fast_refresh_lambda})')
    
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers, screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_title_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a title tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('entities', 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    entities_config = config.get("entities", "")
    entity_values = format_entity_value(entities_config)
    entity_cpp = format_entity_cpp(entity_values)
    requires_fast_refresh = (
        config["requires_fast_refresh"] if "requires_fast_refresh" in config
        else _get_animation_fast_refresh(config)
    )
    
    tile_cpp = f'new TitleTile({x}, {y}, {display_cpp}, {entity_cpp})'
    
    modifiers = []
    context = f"Screen '{screen_id}', Tile at ({x}, {y})" if screen_id else f"Tile at ({x}, {y})"
    fast_refresh_lambda = build_fast_refresh_lambda(requires_fast_refresh, context)
    if fast_refresh_lambda:
        modifiers.append(f'setRequiresFastRefreshFunc({fast_refresh_lambda})')
        
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers, screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_move_page_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a move page tile."""
    # MovePageTile display: int, int, string, Color, font
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('entities', 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    destination = config.get("destination", "")
    dynamic_entry = config.get("dynamic_entry", None)
    
    tile_cpp = f'new MovePageTile({x}, {y}, {display_cpp}, &id({destination}))'
    
    modifiers = []
    if dynamic_entry:
        dynamic_entity = dynamic_entry.get("dynamic_entity", "")
        value = dynamic_entry.get("value", "")
        if dynamic_entity and value:
            values_cpp = format_entity_cpp(value)
            modifiers.append(f'setDynamicEntry("{dynamic_entity}", {values_cpp})')
        else:
            raise ValueError(f"Screen '{screen_id}', Tile at ({x}, {y}): dynamic_entry must have both 'dynamic_entity' and 'value'")
    
    tile_cpp = _apply_modifiers(tile_cpp, config, modifiers, screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_function_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a function tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('entities', 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    on_press = config.get("on_press", None)
    on_release = config.get("on_release", None)
    
    on_press_cpp = format_single_function(on_press, available_scripts, []) if on_press else "nullptr"
    on_release_cpp = format_single_function(on_release, available_scripts, []) if on_release else "nullptr"
    
    if on_release:
        tile_cpp = f'new FunctionTile({x}, {y}, {display_cpp}, {on_press_cpp}, {on_release_cpp})'
    else:
        tile_cpp = f'new FunctionTile({x}, {y}, {display_cpp}, {on_press_cpp})'
    
    tile_cpp = _apply_modifiers(tile_cpp, config, screen_id=screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_toggle_entity_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a toggle entity tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), (['name', 'presentation_name'], 'string'), ('is_on', 'bool')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    dynamic_entity = config.get("dynamic_entity", "")
    entity = config.get("entity", "")
    presentation_name = config.get("presentation_name", "")
    initially_chosen = config.get("initially_chosen", False)
    
    if not dynamic_entity:
        raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}) must have 'dynamic_entity' field")
    if not entity:
        raise ValueError(f"Screen '{screen_id}', toggle_entity tile at ({x}, {y}) must have 'entity' field")
    
    initially_chosen_cpp = "true" if initially_chosen else "false"
    
    entities_cpp = format_entity_cpp(entity)
    
    tile_cpp = f'new ToggleEntityTile({x}, {y}, {display_cpp}, "{dynamic_entity}", {entities_cpp}, "{presentation_name}", {initially_chosen_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config, screen_id=screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_cycle_entity_tile(config, available_scripts, screen_id=None):
    """Generate C++ for a cycle entity tile."""
    _display_params = [('x_start', 'int'), ('x_end', 'int'), ('y_start', 'int'), ('y_end', 'int'), ('name', 'string'), (['options', 'entities'], 'string[]')]
    x, y, display_cpp = _generate_base_tile_args(config, available_scripts, _display_params)
    display_cpp = _override_display_with_image(display_cpp, config, _display_params)
    
    dynamic_entity = config.get("dynamic_entity", "")
    options = config.get("options", [])
    reset_on_leave = config.get("reset_on_leave", False)
    
    if not dynamic_entity:
        raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}) must have 'dynamic_entity' field")
    if not options or len(options) == 0:
        raise ValueError(f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}) must have 'options' list with at least one item")
    
    options_cpp_pairs = []
    
    for option_item in options:
        if isinstance(option_item, dict):
            entity = option_item.get("entity", "")
            label = option_item.get("label", "")
            if entity and label:
                entities_cpp = format_entity_cpp(entity)
                options_cpp_pairs.append(f'{{ {entities_cpp}, "{label}" }}')
            else:
                raise ValueError(f"Screen '{screen_id}', each option item must have both 'entity' and 'label' fields at ({x}, {y})")
        else:
            raise ValueError(f"Screen '{screen_id}', options must be dicts with 'entity' and 'label' fields at ({x}, {y})")
    
    options_cpp = "{ " + ", ".join(options_cpp_pairs) + " }"
    reset_on_leave_cpp = "true" if reset_on_leave else "false"
    
    tile_cpp = f'new CycleEntityTile({x}, {y}, {display_cpp}, "{dynamic_entity}", {options_cpp}, {reset_on_leave_cpp})'
    tile_cpp = _apply_modifiers(tile_cpp, config, screen_id=screen_id)
    tile_cpp += ','
    return tile_cpp


def generate_tile_cpp(tile: dict, available_scripts=None, screen_id=None) -> str:
    """Generate C++ code for a single tile."""
    if TileType.HA_ACTION.value in tile:
        return generate_action_tile(tile[TileType.HA_ACTION.value], available_scripts, screen_id)
    elif TileType.MOVE_PAGE.value in tile:
        return generate_move_page_tile(tile[TileType.MOVE_PAGE.value], available_scripts, screen_id)
    elif TileType.TITLE.value in tile:
        return generate_title_tile(tile[TileType.TITLE.value], available_scripts, screen_id)
    elif TileType.FUNCTION.value in tile:
        return generate_function_tile(tile[TileType.FUNCTION.value], available_scripts, screen_id)
    elif TileType.TOGGLE_ENTITY.value in tile:
        return generate_toggle_entity_tile(tile[TileType.TOGGLE_ENTITY.value], available_scripts, screen_id)
    elif TileType.CYCLE_ENTITY.value in tile:
        return generate_cycle_entity_tile(tile[TileType.CYCLE_ENTITY.value], available_scripts, screen_id)
    else:
        return f'// Unknown tile structure: {list(tile.keys())}'
