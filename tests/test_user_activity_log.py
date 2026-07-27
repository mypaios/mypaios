import os
import json
import pytest
import services.user_activity_log as user_activity_log

def test_user_activity_log_lifecycle(tmp_path, monkeypatch):
    # Set a temp log path
    log_file = tmp_path / "user-activity.jsonl"
    monkeypatch.setattr(user_activity_log, "_LOG_PATH", str(log_file))
    
    # Assert logs initially empty
    assert user_activity_log.get_logs() == []
    
    # Log some events
    user_activity_log.log("click", {"element": "button#btn", "text": "Save"})
    user_activity_log.log("chat_message", {"role": "user", "content": "hello"})
    
    # Retrieve logs and assert
    logs = user_activity_log.get_logs()
    assert len(logs) == 2
    
    # Newest first
    assert logs[0]["type"] == "chat_message"
    assert logs[0]["details"]["role"] == "user"
    assert logs[1]["type"] == "click"
    assert logs[1]["details"]["element"] == "button#btn"
    
    # Test trim limit
    monkeypatch.setattr(user_activity_log, "_MAX_BYTES", 10)  # extremely small to trigger trim
    monkeypatch.setattr(user_activity_log, "_KEEP_LINES", 1)
    
    # Write another event to trigger the size check and trim
    user_activity_log.log("input_change", {"value": "new text"})
    
    trimmed_logs = user_activity_log.get_logs()
    assert len(trimmed_logs) == 1
    assert trimmed_logs[0]["type"] == "input_change"
    
    # Test clear
    user_activity_log.clear_logs()
    assert user_activity_log.get_logs() == []
    assert not os.path.exists(str(log_file))

def test_user_activity_log_errors(tmp_path, monkeypatch):
    log_file = tmp_path / "user-activity.jsonl"
    monkeypatch.setattr(user_activity_log, "_LOG_PATH", str(log_file))
    
    # Log backend and frontend errors
    user_activity_log.log("backend_error", {"status": 500, "path": "/api/chat", "method": "POST"})
    user_activity_log.log("frontend_error", {"message": "TypeError: Cannot read properties", "source": "app.js", "line": 42})
    
    logs = user_activity_log.get_logs()
    assert len(logs) == 2
    assert logs[0]["type"] == "frontend_error"
    assert logs[0]["details"]["message"] == "TypeError: Cannot read properties"
    assert logs[1]["type"] == "backend_error"
    assert logs[1]["details"]["status"] == 500
