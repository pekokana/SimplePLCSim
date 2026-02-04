import os

def rename_entity(app_state, entity_type: str, old_name: str, new_name: str):
    """
    名前変更時に project_files / YAMLファイル名 / orchestrator services を安全に追従させる
    """
    if old_name == new_name:
        return

    ent_map = app_state.project_files.get(entity_type, {})
    if old_name not in ent_map:
        return

    # メモリ上のキー変更
    ent_yaml = ent_map.pop(old_name)
    ent_yaml["name"] = new_name
    ent_map[new_name] = ent_yaml

    # Orchestrator services 側の参照更新
    for svc in app_state.config_data.get("services", []):
        if svc.get("type") == entity_type and svc.get("name") == old_name:
            svc["name"] = new_name

    # YAMLファイル名変更
    base_dir = app_state.project_root / entity_type
    old_path = base_dir / f"{old_name}.yaml"
    new_path = base_dir / f"{new_name}.yaml"

    if old_path.exists():
        old_path.rename(new_path)
