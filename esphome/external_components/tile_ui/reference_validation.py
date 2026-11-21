"""Reference, tile grid position, and screen reachability validators."""
from .data_collection import collect_dynamic_entities
from .schema import TileType
from .tile_images import is_image_param_type, normalize_image_param_id, _get_script_params

def _validate_image_references(
    screens: list[dict],
    available_images: set,
    available_scripts: dict | None = None,
) -> None:
    """Validate that every image reference in every tile's display_assets list (including animation
    steps and legacy 'image' field) and image-typed display script parameters exists in the global
    images store. Icon entries (with 'icon' key) are skipped since they do not reference the image
    store.
    """
    for screen in screens:
        screen_id = screen.get("id", "")
        for tile in screen.get("tiles", []):
            tile_type = list(tile.keys())[0]
            config = tile[tile_type]
            x = config.get("x", 0)
            y = config.get("y", 0)

            # Check legacy image field if present
            legacy_img = config.get("image")
            if legacy_img and legacy_img != 'none' and legacy_img not in available_images:
                available_list = ", ".join(sorted(available_images)) if available_images else "(none)"
                raise ValueError(
                    f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                    f"image '{legacy_img}' is not defined in the images store. "
                    f"Available images: {available_list}"
                )

            for entry in (config.get("display_assets") or []):
                if not isinstance(entry, dict):
                    continue
                # Skip icon entries — they don't reference image store IDs
                if entry.get("icon"):
                    pass
                else:
                    img_id = entry.get("image", "")
                    if img_id and img_id != 'none' and img_id not in available_images:
                        available_list = ", ".join(sorted(available_images)) if available_images else "(none)"
                        raise ValueError(
                            f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                            f"image '{img_id}' is not defined in the images store. "
                            f"Available images: {available_list}"
                        )

                # Check animation steps if any step overrides or provides 'image'
                anim = entry.get("animation")
                if isinstance(anim, dict):
                    for step_idx, step in enumerate(anim.get("steps") or []):
                        if isinstance(step, dict):
                            step_img = step.get("image")
                            if step_img and step_img != 'none' and step_img not in available_images:
                                available_list = ", ".join(sorted(available_images)) if available_images else "(none)"
                                raise ValueError(
                                    f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                                    f"animation step {step_idx} image '{step_img}' is not defined in the images store. "
                                    f"Available images: {available_list}"
                                )

            # Check image-typed parameters on display scripts
            if available_scripts and isinstance(config.get("display"), list):
                for item in config["display"]:
                    if not isinstance(item, dict):
                        continue
                    for script_id, params in item.items():
                        if not isinstance(params, dict):
                            continue
                        script_params = _get_script_params(available_scripts, script_id)
                        for param_name, param_val in params.items():
                            if is_image_param_type(script_params.get(param_name)):
                                img_id = normalize_image_param_id(param_val)
                                if img_id and img_id not in ('none', 'nullptr') and img_id not in available_images:
                                    available_list = ", ".join(sorted(available_images)) if available_images else "(none)"
                                    raise ValueError(
                                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                                        f"script '{script_id}' parameter '{param_name}' image '{img_id}' "
                                        f"is not defined in the images store. "
                                        f"Available images: {available_list}"
                                    )


def _validate_screen_image_references(screens: list[dict], available_screen_images: set) -> None:
    """Validate that every image reference in screen background entries exists in screen_images."""
    for screen in screens:
        screen_id = screen.get("id", "")
        for bg_idx, entry in enumerate(screen.get("background") or []):
            if not isinstance(entry, dict):
                continue
            img_id = entry.get("image", "")
            if img_id and img_id != 'none' and img_id not in available_screen_images:
                available_list = ", ".join(sorted(available_screen_images)) if available_screen_images else "(none)"
                raise ValueError(
                    f"Screen '{screen_id}', background entry {bg_idx}: "
                    f"image '{img_id}' is not defined in screen_images. "
                    f"Available screen images: {available_list}"
                )


def _validate_dynamic_entity_references(
    screens: list[dict],
    declared_set: set[str] | None,
    fixed_set: set[str] | None = None,
) -> None:
    """Validate that every dynamic_entity reference is declared and fixed entities are not mutated.

    Checks the following locations where a dynamic_entity name can appear:
    - toggle_entity / cycle_entity  -> tile.dynamic_entity (runtime-mutating)
    - ha_action                     -> tile.long_dynamic_entity (runtime-mutating)
    - move_page                     -> tile.dynamic_entry.dynamic_entity (runtime-mutating)
    - entity-list tiles             -> tile.entities[i].dynamic_entity (read-only)
    - any tile type                 -> tile.activation_var.dynamic_entity (read-only)
    """
    fixed = fixed_set or set()

    for screen in screens:
        screen_id = screen.get("id", "")
        for tile in screen.get("tiles", []):
            tile_type = list(tile.keys())[0]
            config = tile[tile_type]
            x = config.get("x", 0)
            y = config.get("y", 0)

            def _check(name: str, location: str, mutates: bool = False) -> None:
                if not name:
                    return
                if declared_set is not None and name not in declared_set:
                    declared_list = ", ".join(sorted(declared_set)) if declared_set else "(none)"
                    raise ValueError(
                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                        f"{location} references dynamic entity '{name}' which is not "
                        f"declared in dynamic_entities. "
                        f"Declared dynamic entities are: {declared_list}"
                    )
                if mutates and name in fixed:
                    raise ValueError(
                        f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): "
                        f"{location} cannot modify fixed dynamic entity '{name}'. "
                        f"Remove its fixed value in dynamic_entities or use a non-fixed dynamic entity."
                    )

            # Direct dynamic_entity field (toggle_entity, cycle_entity — mutates at runtime)
            direct = config.get("dynamic_entity", "")
            if direct:
                _check(direct, "dynamic_entity", mutates=True)
            if config.get("long_dynamic_entity"):
                _check(config["long_dynamic_entity"], "long_dynamic_entity", mutates=True)

            # entities list (read-only)
            tile_dyn_names: list[str] = []
            for i, entry in enumerate(config.get("entities", [])):
                if isinstance(entry, dict):
                    de = entry.get("dynamic_entity", "")
                    if de:
                        _check(de, f"entities[{i}].dynamic_entity", mutates=False)
                        tile_dyn_names.append(de)

            # display_page_if_no_entity requires at least one runtime (non-fixed) dynamic entity
            if (
                tile_type == TileType.HA_ACTION.value
                and config.get("display_page_if_no_entity")
                and tile_dyn_names
                and fixed
                and all(de in fixed for de in tile_dyn_names)
            ):
                raise ValueError(
                    f"Screen '{screen_id}', ha_action tile at ({x}, {y}): "
                    f"display_page_if_no_entity cannot be used when all referenced dynamic entities "
                    f"({', '.join(tile_dyn_names)}) have fixed values"
                )

            # activation_var.dynamic_entity (read-only)
            activation_var = config.get("activation_var")
            if isinstance(activation_var, dict):
                de = activation_var.get("dynamic_entity", "")
                if de:
                    _check(de, "activation_var.dynamic_entity", mutates=False)

            # dynamic_entry.dynamic_entity (move_page — mutates at runtime)
            dynamic_entry = config.get("dynamic_entry")
            if dynamic_entry:
                entries = dynamic_entry if isinstance(dynamic_entry, list) else [dynamic_entry]
                for idx, entry in enumerate(entries):
                    if isinstance(entry, dict):
                        de = entry.get("dynamic_entity", "")
                        if de:
                            label = f"dynamic_entry[{idx}].dynamic_entity" if isinstance(dynamic_entry, list) else "dynamic_entry.dynamic_entity"
                            _check(de, label, mutates=True)

            # cycle_entity options[i].dynamic_entity (read-only — must be a fixed dynamic entity)
            if tile_type == TileType.CYCLE_ENTITY.value:
                for idx, option in enumerate(config.get("options", [])):
                    if isinstance(option, dict) and option.get("dynamic_entity"):
                        de = option["dynamic_entity"]
                        _check(de, f"options[{idx}].dynamic_entity", mutates=False)
                        if de not in fixed:
                            raise ValueError(
                                f"Screen '{screen_id}', cycle_entity tile at ({x}, {y}): "
                                f"options[{idx}].dynamic_entity references '{de}' which is not a fixed dynamic entity. "
                                f"Bind '{de}' to fixed entity ID(s) in dynamic_entities."
                            )


def _validate_tile_positions(screen_id, tiles):
    """Validate tile positions and stacking rules.
    
    Rules:
    1. Multiple tiles can exist at the same (x, y) position.
    2. If multiple tiles exist at the same position, they MUST all have an 'activation_var'.
    3. All tiles at the same position MUST use the same 'dynamic_entity' in their 'activation_var'.
    4. Tiles with spans occupy multiple grid cells. Overlap rules apply to all occupied cells.
    """
    # Map each grid cell to the list of tiles occupying it
    grid_cells = {} # (x, y) -> list of (tile_type, config)
    
    for tile in tiles:
        tile_type = list(tile.keys())[0]
        config = tile[tile_type]
        
        try:
            x = int(config.get("x", 0))
            y = int(config.get("y", 0))
            x_span = int(config.get("x_span", 1))
            y_span = int(config.get("y_span", 1))
        except (ValueError, TypeError):
            raise ValueError(f"Screen '{screen_id}', {tile_type} tile: coordinates and spans must be integers")
        
        if x_span < 1:
            raise ValueError(f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): x_span must be at least 1")
        if y_span < 1:
            raise ValueError(f"Screen '{screen_id}', {tile_type} tile at ({x}, {y}): y_span must be at least 1")
            
        # Add tile to all cells it occupies
        for i in range(x_span):
            for j in range(y_span):
                pos_key = (x + i, y + j)
                if pos_key not in grid_cells:
                    grid_cells[pos_key] = []
                grid_cells[pos_key].append((tile_type, config))

    for pos_key, tile_list in grid_cells.items():
        if len(tile_list) > 1:
            x, y = pos_key
            
            # Check if all have activation_var
            for t_type, t_config in tile_list:
                if not t_config.get("activation_var"):
                    raise ValueError(
                        f"Screen '{screen_id}': Overlapping tiles at ({x}, {y}) but "
                        f"{t_type} tile is missing 'activation_var'. "
                        f"All overlapping tiles must have an 'activation_var' to control visibility."
                    )
            
            # Check if all have the same dynamic_entity and unique value sets
            first_var = tile_list[0][1].get("activation_var", {}).get("dynamic_entity")
            seen_value_sets = [] # List of sets of values
            
            for t_type, t_config in tile_list:
                act_var = t_config.get("activation_var", {})
                current_var = act_var.get("dynamic_entity")
                
                if current_var != first_var:
                    raise ValueError(
                        f"Screen '{screen_id}': Overlapping tiles at ({x}, {y}) must use the same "
                        f"activation variable (dynamic_entity). Found '{first_var}' and '{current_var}'."
                    )
                
                # Check for duplicate value sets (ignore order)
                val = act_var.get("value", "")
                if isinstance(val, str):
                    current_vals = set(v.strip() for v in val.split(","))
                elif isinstance(val, list):
                    current_vals = set(str(v).strip() for v in val)
                else:
                    current_vals = {str(val)}
            
                if current_vals in seen_value_sets:
                     val_str = ", ".join(sorted(list(current_vals)))
                     raise ValueError(
                        f"Screen '{screen_id}': Overlapping tiles at ({x}, {y}) have the same "
                        f"exact activation values: [{val_str}] for variable '{first_var}'. "
                        f"Each overlapping tile must have a unique set of activation values."
                    )
                seen_value_sets.append(current_vals)


def _validate_base_screen_reachability(screens, base_screen_id, valid_screen_ids):
    """Validate that all non-TEMPORARY screens can navigate back to the BASE screen.
    
    Builds a directed graph of screen connections via move_page tiles and checks
    that every non-TEMPORARY screen has a path to the BASE screen.
    
    Note: TEMPORARY screens automatically return to the BASE screen, so they are
    not required to have explicit move_page navigation back to BASE.
    
    Args:
        screens: List of screen configurations
        base_screen_id: ID of the BASE screen
        valid_screen_ids: Set of all valid screen IDs
        
    Raises:
        ValueError: If any non-TEMPORARY screen cannot reach the BASE screen
    """
    from collections import deque
    
    # Collect TEMPORARY screen IDs
    temporary_screen_ids = set()
    for screen in screens:
        flags = screen.get("flags", [])
        if "TEMPORARY" in flags:
            temporary_screen_ids.add(screen.get("id", ""))
    
    # Build a graph: screen_id -> set of screens it can navigate to
    navigation_graph = {screen_id: set() for screen_id in valid_screen_ids}
    
    for screen in screens:
        screen_id = screen.get("id", "")
        tiles = screen.get("tiles", [])
        
        for tile in tiles:
            tile_type = list(tile.keys())[0]
            if tile_type == TileType.MOVE_PAGE.value:
                config = tile[tile_type]
                destination = config.get("destination", "")
                if destination and destination in valid_screen_ids:
                    navigation_graph[screen_id].add(destination)
            elif tile_type == TileType.HA_ACTION.value:
                destination = tile[tile_type].get("long_destination", "")
                if destination and destination in valid_screen_ids:
                    navigation_graph[screen_id].add(destination)
    
    # For each non-TEMPORARY, non-BASE screen, check if it can reach BASE screen
    # (either directly, via TEMPORARY screens, or via other navigation)
    unreachable_screens = []
    
    for screen_id in valid_screen_ids:
        # Skip BASE screen (it's the target)
        if screen_id == base_screen_id:
            continue
        
        # Skip TEMPORARY screens (they automatically return to BASE)
        if screen_id in temporary_screen_ids:
            continue
        
        # BFS to find if we can reach BASE screen or a TEMPORARY screen from this screen
        visited = set()
        queue = deque([screen_id])
        can_reach_base = False
        
        while queue:
            current = queue.popleft()
            # Reached BASE directly
            if current == base_screen_id:
                can_reach_base = True
                break
            # Reached a TEMPORARY screen (which will auto-return to BASE)
            if current in temporary_screen_ids:
                can_reach_base = True
                break
            
            if current in visited:
                continue
            visited.add(current)
            
            for neighbor in navigation_graph.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        if not can_reach_base:
            unreachable_screens.append(screen_id)
    
    if unreachable_screens:
        raise ValueError(
            f"The following screens cannot navigate back to the BASE screen '{base_screen_id}': "
            f"{', '.join(sorted(unreachable_screens))}. "
            f"Each non-TEMPORARY screen must have a path (via move_page tiles) to reach the BASE screen or a TEMPORARY screen."
        )


