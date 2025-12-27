#!/usr/bin/env python3
"""
Simple Touchscreen Scheduler for Jetson Orin Nano Super
Big buttons, minimal UI, iPhone web remote
"""

import sys
import os
import json
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QStackedWidget,
    QGridLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont

# Files
DATA_FILE = Path.home() / ".touchscreen_scheduler" / "tasks.json"
CONFIG_FILE = Path.home() / ".touchscreen_scheduler" / "config.json"

# Display config
DISPLAY_OUTPUT = "DP-1"
TOUCH_DEVICE = "WaveShare WaveShare"

ROTATION_MATRICES = {
    "normal": "1 0 0 0 1 0 0 0 1",
    "left": "0 -1 1 1 0 0 0 0 1",
    "inverted": "-1 0 1 0 -1 1 0 0 1",
    "right": "0 1 0 -1 0 1 0 0 1",
}

# Flask app for iPhone remote
flask_app = Flask(__name__)
flask_app.config['TEMPLATES_AUTO_RELOAD'] = True

# Signal bridge for thread-safe UI updates
class SignalBridge(QObject):
    task_added = pyqtSignal(dict)
    refresh_requested = pyqtSignal()

signal_bridge = SignalBridge()

# Global reference to tasks
tasks_list = []

def load_tasks():
    global tasks_list
    try:
        if DATA_FILE.exists():
            with open(DATA_FILE, 'r') as f:
                tasks_list = json.load(f)
    except:
        tasks_list = []
    return tasks_list

def save_tasks():
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(tasks_list, f, indent=2)
    except Exception as e:
        print(f"Save failed: {e}")

def install_cron(task):
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        current = result.stdout if result.returncode == 0 else ""
        job = f"{task['cron']} {task['command']} # scheduler_id:{task['id']}\n"
        new_cron = current.rstrip() + "\n" + job
        proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
        proc.communicate(input=new_cron)
    except Exception as e:
        print(f"Cron install failed: {e}")

def remove_cron(task):
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return
        lines = [l for l in result.stdout.splitlines() if f"scheduler_id:{task['id']}" not in l]
        proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
        proc.communicate(input="\n".join(lines) + "\n")
    except Exception as e:
        print(f"Cron remove failed: {e}")


# ============== FLASK WEB INTERFACE ==============

IPHONE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>Scheduler Remote</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        h1 {
            text-align: center;
            color: #e94560;
            margin-bottom: 30px;
            font-size: 28px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            color: #888;
            margin-bottom: 8px;
            font-size: 14px;
        }
        input, textarea, select {
            width: 100%;
            padding: 16px;
            border: 2px solid #2a2a4e;
            border-radius: 12px;
            background: #16213e;
            color: #fff;
            font-size: 18px;
        }
        input[type="time"] {
            font-size: 24px;
            padding: 20px;
        }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: #e94560;
        }
        textarea { min-height: 80px; resize: vertical; }
        .time-row {
            display: flex;
            gap: 12px;
            align-items: center;
            margin-bottom: 20px;
        }
        .time-row input { flex: 1; }
        .time-row .time-label {
            color: #e94560;
            font-size: 16px;
            font-weight: bold;
        }
        .schedules {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 25px;
        }
        .sched-btn {
            padding: 20px;
            border: 2px solid #2a2a4e;
            border-radius: 12px;
            background: #16213e;
            color: #fff;
            font-size: 16px;
            cursor: pointer;
            text-align: center;
        }
        .sched-btn.active {
            background: #e94560;
            border-color: #e94560;
        }
        .sched-btn .icon { font-size: 28px; display: block; margin-bottom: 5px; }
        .submit-btn {
            width: 100%;
            padding: 20px;
            background: linear-gradient(90deg, #e94560, #ff6b6b);
            border: none;
            border-radius: 12px;
            color: #fff;
            font-size: 20px;
            font-weight: bold;
            cursor: pointer;
        }
        .submit-btn:active { transform: scale(0.98); }
        .tasks { margin-top: 30px; }
        .task-card {
            background: #16213e;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .task-info h3 { font-size: 18px; margin-bottom: 5px; }
        .task-info p { color: #888; font-size: 14px; }
        .delete-btn {
            background: rgba(233,69,96,0.2);
            color: #e94560;
            border: none;
            width: 44px;
            height: 44px;
            border-radius: 10px;
            font-size: 20px;
            cursor: pointer;
        }
        .msg {
            text-align: center;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 10px;
            display: none;
        }
        .msg.success { background: #1a3a1a; color: #4ade80; display: block; }
        .msg.error { background: #3a1a1a; color: #ff6b6b; display: block; }
    </style>
</head>
<body>
    <h1>📅 Scheduler</h1>
    
    <div id="message" class="msg"></div>
    
    <form id="taskForm">
        <div class="form-group">
            <label>Task Name</label>
            <input type="text" id="name" placeholder="What to call this task" required>
        </div>
        
        <div class="form-group">
            <label>Command</label>
            <textarea id="command" placeholder="Command to run..." required></textarea>
        </div>
        
        <label>Time (for Daily/Weekly)</label>
        <div class="time-row">
            <input type="time" id="taskTime" value="09:00">
            <span class="time-label">⏰</span>
        </div>
        
        <label>Schedule</label>
        <div class="schedules">
            <div class="sched-btn" data-schedule="hourly">
                <span class="icon">🕐</span>Hourly
            </div>
            <div class="sched-btn active" data-schedule="daily">
                <span class="icon">📅</span>Daily
            </div>
            <div class="sched-btn" data-schedule="weekly">
                <span class="icon">📆</span>Weekly
            </div>
            <div class="sched-btn" data-schedule="reboot">
                <span class="icon">🔄</span>Startup
            </div>
        </div>
        
        <button type="submit" class="submit-btn">Add Task</button>
    </form>
    
    <div class="tasks" id="taskList"></div>
    
    <script>
        let selectedSchedule = 'daily';
        
        function getCron() {
            const time = document.getElementById('taskTime').value;
            const [hour, minute] = time.split(':');
            
            switch(selectedSchedule) {
                case 'hourly': return '0 * * * *';
                case 'daily': return minute + ' ' + hour + ' * * *';
                case 'weekly': return minute + ' ' + hour + ' * * 1';
                case 'reboot': return '@reboot';
                default: return '0 * * * *';
            }
        }
        
        function getDisplayName() {
            const time = document.getElementById('taskTime').value;
            switch(selectedSchedule) {
                case 'hourly': return 'Every Hour';
                case 'daily': return 'Daily at ' + time;
                case 'weekly': return 'Weekly Mon ' + time;
                case 'reboot': return 'At Startup';
                default: return selectedSchedule;
            }
        }
        
        document.querySelectorAll('.sched-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.sched-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedSchedule = btn.dataset.schedule;
            });
        });
        
        document.getElementById('taskForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('name').value;
            const command = document.getElementById('command').value;
            const cron = getCron();
            const displayName = getDisplayName();
            
            try {
                const res = await fetch('/api/tasks', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name, command, schedule: displayName, cron: cron})
                });
                const data = await res.json();
                
                if (data.success) {
                    showMsg('Task added!', 'success');
                    document.getElementById('name').value = '';
                    document.getElementById('command').value = '';
                    loadTasks();
                } else {
                    showMsg('Failed to add task', 'error');
                }
            } catch (err) {
                showMsg('Connection error', 'error');
            }
        });
        
        async function loadTasks() {
            try {
                const res = await fetch('/api/tasks');
                const tasks = await res.json();
                const list = document.getElementById('taskList');
                list.innerHTML = tasks.map(t => `
                    <div class="task-card">
                        <div class="task-info">
                            <h3>${t.name}</h3>
                            <p>${t.schedule_display}</p>
                        </div>
                        <button class="delete-btn" onclick="deleteTask(${t.id})">✕</button>
                    </div>
                `).join('');
            } catch (err) {
                console.error(err);
            }
        }
        
        async function deleteTask(id) {
            await fetch('/api/tasks/' + id, {method: 'DELETE'});
            loadTasks();
        }
        
        function showMsg(text, type) {
            const msg = document.getElementById('message');
            msg.textContent = text;
            msg.className = 'msg ' + type;
            setTimeout(() => msg.className = 'msg', 3000);
        }
        
        loadTasks();
    </script>
</body>
</html>
'''

@flask_app.route('/')
def index():
    return render_template_string(IPHONE_HTML)

@flask_app.route('/api/tasks', methods=['GET'])
def get_tasks():
    return jsonify(tasks_list)

@flask_app.route('/api/tasks', methods=['POST'])
def add_task():
    global tasks_list
    data = request.json
    
    task = {
        'id': datetime.now().timestamp(),
        'name': data['name'],
        'command': data['command'],
        'schedule_type': data['schedule'],
        'schedule_display': data['schedule'],  # Now includes time from client
        'cron': data['cron'],
        'created': datetime.now().isoformat()
    }
    
    tasks_list.append(task)
    save_tasks()
    install_cron(task)
    
    # Signal UI to refresh
    signal_bridge.task_added.emit(task)
    
    return jsonify({'success': True, 'task': task})

@flask_app.route('/api/tasks/<float:task_id>', methods=['DELETE'])
def delete_task(task_id):
    global tasks_list
    task = next((t for t in tasks_list if t['id'] == task_id), None)
    if task:
        remove_cron(task)
        tasks_list = [t for t in tasks_list if t['id'] != task_id]
        save_tasks()
        signal_bridge.refresh_requested.emit()
    return jsonify({'success': True})

def run_flask():
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


# ============== PYQT UI ==============

class TaskCard(QFrame):
    delete_clicked = pyqtSignal(dict)
    
    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("taskCard")
        self.setMinimumHeight(200)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        
        # Task info
        info = QVBoxLayout()
        info.setSpacing(15)
        
        name = QLabel(task.get('name', 'Task'))
        name.setObjectName("taskName")
        info.addWidget(name)
        
        sched = QLabel(task.get('schedule_display', ''))
        sched.setObjectName("taskSched")
        info.addWidget(sched)
        
        layout.addLayout(info, 1)
        
        # Delete button
        delete_btn = QPushButton("✕")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.setFixedSize(120, 120)
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.task))
        layout.addWidget(delete_btn)


class SchedulerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        global tasks_list
        tasks_list = load_tasks()
        self.config = self.load_config()
        self.current_rotation = self.config.get("rotation", "normal")
        
        # Get IP for display (before setup_ui)
        try:
            ip = subprocess.check_output("hostname -I | awk '{print $1}'", shell=True).decode().strip()
            self.ip_address = ip
        except:
            self.ip_address = "unknown"
        
        self.setup_ui()
        self.apply_styles()
        self.apply_rotation(self.current_rotation, save=False)
        
        # Connect signals from Flask thread
        signal_bridge.task_added.connect(self.on_task_added)
        signal_bridge.refresh_requested.connect(self.refresh_tasks)
        
        # Start Flask in background
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
    
    def load_config(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def save_config(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f)
        except:
            pass
    
    def setup_ui(self):
        self.setWindowTitle("Scheduler")
        
        main = QWidget()
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        self.stack.addWidget(self.create_home())
        self.stack.addWidget(self.create_settings())
        
    def create_home(self):
        screen = QWidget()
        layout = QVBoxLayout(screen)
        layout.setContentsMargins(50, 60, 50, 50)
        layout.setSpacing(40)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("Scheduler")
        title.setObjectName("title")
        header.addWidget(title)
        
        header.addStretch()
        
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("iconBtn")
        settings_btn.setFixedSize(140, 140)
        settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        header.addWidget(settings_btn)
        
        layout.addLayout(header)
        
        # iPhone connection info
        self.ip_label = QLabel(f"📱 Connect: http://192.168.1.50:5000")
        self.ip_label.setObjectName("ipLabel")
        layout.addWidget(self.ip_label)
        
        # Task list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("taskScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.task_container = QWidget()
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(0, 0, 0, 0)
        self.task_layout.setSpacing(30)
        self.task_layout.addStretch()
        
        scroll.setWidget(self.task_container)
        layout.addWidget(scroll, 1)
        
        self.refresh_tasks()
        
        return screen
    
    def create_settings(self):
        screen = QWidget()
        layout = QVBoxLayout(screen)
        layout.setContentsMargins(50, 60, 50, 50)
        layout.setSpacing(40)
        
        # Header
        header = QHBoxLayout()
        
        back_btn = QPushButton("←")
        back_btn.setObjectName("iconBtn")
        back_btn.setFixedSize(140, 140)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        header.addWidget(back_btn)
        
        title = QLabel("Settings")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        
        layout.addLayout(header)
        
        # Rotation
        rot_label = QLabel("Screen Rotation")
        rot_label.setObjectName("sectionLabel")
        layout.addWidget(rot_label)
        
        rot_grid = QGridLayout()
        rot_grid.setSpacing(25)
        
        rotations = [
            ("↑\nNormal", "normal"),
            ("←\nLeft", "left"),
            ("→\nRight", "right"),
            ("↓\nFlip", "inverted"),
        ]
        
        self.rot_buttons = {}
        for i, (label, rot) in enumerate(rotations):
            btn = QPushButton(label)
            btn.setObjectName("bigBtn")
            btn.setCheckable(True)
            btn.setMinimumHeight(220)
            btn.clicked.connect(lambda _, r=rot: self.apply_rotation(r))
            rot_grid.addWidget(btn, i // 2, i % 2)
            self.rot_buttons[rot] = btn
        
        if self.current_rotation in self.rot_buttons:
            self.rot_buttons[self.current_rotation].setChecked(True)
        
        layout.addLayout(rot_grid)
        layout.addStretch()
        
        # Exit
        exit_btn = QPushButton("Exit App")
        exit_btn.setObjectName("exitBtn")
        exit_btn.setMinimumHeight(160)
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)
        
        return screen
    
    def apply_rotation(self, rotation, save=True):
        try:
            subprocess.run(["xrandr", "--output", DISPLAY_OUTPUT, "--rotate", rotation], 
                         check=True, capture_output=True)
            matrix = ROTATION_MATRICES.get(rotation, ROTATION_MATRICES["normal"])
            subprocess.run(["xinput", "set-prop", TOUCH_DEVICE, 
                          "Coordinate Transformation Matrix"] + matrix.split(),
                         check=True, capture_output=True)
            
            for r, btn in self.rot_buttons.items():
                btn.setChecked(r == rotation)
            
            self.current_rotation = rotation
            if save:
                self.config["rotation"] = rotation
                self.save_config()
        except Exception as e:
            print(f"Rotation failed: {e}")
    
    def on_task_added(self, task):
        self.refresh_tasks()
    
    def refresh_tasks(self):
        global tasks_list
        
        # Clear existing
        while self.task_layout.count() > 1:
            item = self.task_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not tasks_list:
            empty = QLabel("No tasks\n\n📱 Add from your iPhone")
            empty.setObjectName("emptyLabel")
            empty.setAlignment(Qt.AlignCenter)
            self.task_layout.insertWidget(0, empty)
        else:
            for task in tasks_list:
                card = TaskCard(task)
                card.delete_clicked.connect(self.delete_task)
                self.task_layout.insertWidget(self.task_layout.count() - 1, card)
        
        # Update IP label
        if hasattr(self, 'ip_label') and hasattr(self, 'ip_address'):
            self.ip_label.setText(f"📱 Connect: http://{self.ip_address}:5000")
    
    def delete_task(self, task):
        global tasks_list
        remove_cron(task)
        tasks_list = [t for t in tasks_list if t['id'] != task['id']]
        save_tasks()
        self.refresh_tasks()
    
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #000000;
                color: #ffffff;
                font-family: 'Noto Sans', sans-serif;
            }
            
            #title {
                font-size: 96px;
                font-weight: bold;
                color: #e94560;
            }
            
            #sectionLabel {
                font-size: 56px;
                color: #888888;
                margin-top: 30px;
            }
            
            #ipLabel {
                font-size: 42px;
                color: #4a90d9;
                background: #0a1525;
                padding: 30px 40px;
                border-radius: 25px;
            }
            
            #iconBtn {
                background-color: #16213e;
                color: #ffffff;
                border: none;
                border-radius: 30px;
                font-size: 72px;
            }
            #iconBtn:pressed {
                background-color: #0f3460;
            }
            
            #bigBtn {
                background-color: #16213e;
                color: #ffffff;
                border: 4px solid #0f3460;
                border-radius: 35px;
                font-size: 52px;
                font-weight: bold;
            }
            #bigBtn:checked {
                background-color: #e94560;
                border-color: #e94560;
            }
            #bigBtn:pressed {
                background-color: #0f3460;
            }
            
            #exitBtn {
                background-color: #1a0505;
                color: #ff6b6b;
                border: 4px solid #3a1515;
                border-radius: 35px;
                font-size: 52px;
            }
            #exitBtn:pressed {
                background-color: #3a1515;
            }
            
            #taskScroll {
                background: transparent;
                border: none;
            }
            #taskScroll QScrollBar:vertical {
                background: #0a0a0a;
                width: 24px;
                border-radius: 12px;
            }
            #taskScroll QScrollBar::handle:vertical {
                background: #e94560;
                border-radius: 12px;
                min-height: 80px;
            }
            #taskScroll QScrollBar::add-line:vertical,
            #taskScroll QScrollBar::sub-line:vertical {
                height: 0;
            }
            
            #taskCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #16213e, stop:1 #0f3460);
                border-radius: 35px;
                border: 3px solid #1a1a3e;
            }
            
            #taskName {
                font-size: 52px;
                font-weight: bold;
                color: #ffffff;
            }
            
            #taskSched {
                font-size: 40px;
                color: #e94560;
            }
            
            #deleteBtn {
                background: rgba(233,69,96,0.3);
                color: #e94560;
                border: none;
                border-radius: 30px;
                font-size: 52px;
                font-weight: bold;
            }
            #deleteBtn:pressed {
                background: #e94560;
                color: white;
            }
            
            #emptyLabel {
                font-size: 56px;
                color: #4a4a6a;
                padding: 120px 0;
            }
        """)


def main():
    QApplication.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
    app = QApplication(sys.argv)
    app.setFont(QFont("Noto Sans", 16))
    
    window = SchedulerApp()
    window.showFullScreen()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
