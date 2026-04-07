from pathlib import Path


def test_main_process_does_not_register_legacy_folder_organize_ipc() -> None:
    main_process = (Path(__file__).resolve().parents[1] / "main.cjs").read_text(encoding="utf-8")
    assert "ipcMain.handle('folder:organize'" not in main_process


def test_preload_does_not_expose_legacy_organize_folder_bridge() -> None:
    preload = (Path(__file__).resolve().parents[1] / "preload.cjs").read_text(encoding="utf-8")
    assert "organizeFolder:" not in preload


def test_main_process_registers_proposal_first_undo_batch_bridge() -> None:
    main_process = (Path(__file__).resolve().parents[1] / "main.cjs").read_text(encoding="utf-8")
    assert "ipcMain.handle('organize:registerUndoBatch'" in main_process
    assert "ipcMain.handle('organize:clearUndoBatch'" in main_process
    assert "if (UNDO_STACK.length > 0)" not in main_process


def test_legacy_undo_compatibility_handlers_are_removed() -> None:
    main_process = (Path(__file__).resolve().parents[1] / "main.cjs").read_text(encoding="utf-8")
    preload = (Path(__file__).resolve().parents[1] / "preload.cjs").read_text(encoding="utf-8")

    assert "ipcMain.handle('organize:undo'" not in main_process
    assert "ipcMain.handle('organize:canUndo'" not in main_process
    assert "undoOrganize:" not in preload
    assert "canUndoOrganize:" not in preload
