#!/usr/bin/env python3
"""
Quote Display with AI Generated Art
Fetches top quote from Reddit /r/quotes and generates matching AI art
Uses Claude to create artistic prompts
Optimized for Waveshare 5.5" AMOLED 1080x1920
"""

import sys
import os
import re
import random
import requests
import urllib.parse
from io import BytesIO
from pathlib import Path

# Debug logging to file
def log(msg):
    with open("/tmp/quote_debug.log", "a") as f:
        f.write(f"{msg}\n")
    print(msg)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSizePolicy, QStackedWidget
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, QRect
from PyQt5.QtGui import QFont, QPixmap, QPalette, QColor, QImage, QPainter, QBrush


class SquareLoadingWidget(QWidget):
    """Loading animation - snake fills until image ready, then rushes to center"""
    
    loading_complete = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_size = 8  # 8x8 grid
        self.filled_squares = []
        self.spiral_path = []
        self.animation_step = 0
        self.image_ready = False
        self.finishing = False
        self.colors = [
            QColor("#ffd700"),  # Gold
            QColor("#ffaa00"),  # Orange gold
            QColor("#ff8800"),  # Orange
            QColor("#ff6600"),  # Deep orange
            QColor("#e94560"),  # Red accent
        ]
        
        # Generate spiral path from outside to inside
        self.generate_spiral_path()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.advance_animation)
    
    def generate_spiral_path(self):
        """Generate a spiral path from edges to center"""
        self.spiral_path = []
        n = self.grid_size
        
        top, bottom, left, right = 0, n - 1, 0, n - 1
        
        while top <= bottom and left <= right:
            # Top row (left to right)
            for col in range(left, right + 1):
                self.spiral_path.append((top, col))
            top += 1
            
            # Right column (top to bottom)
            for row in range(top, bottom + 1):
                self.spiral_path.append((row, right))
            right -= 1
            
            # Bottom row (right to left)
            if top <= bottom:
                for col in range(right, left - 1, -1):
                    self.spiral_path.append((bottom, col))
                bottom -= 1
            
            # Left column (bottom to top)
            if left <= right:
                for row in range(bottom, top - 1, -1):
                    self.spiral_path.append((row, left))
                left += 1
        
    def start_animation(self):
        """Start the loading animation"""
        self.filled_squares = []
        self.animation_step = 0
        self.image_ready = False
        self.waiting_for_image = False
        self.timer.start(400)  # Slow: ~25sec total
        self.update()
    
    def signal_image_ready(self):
        """Called when image is ready - rush to finish"""
        self.image_ready = True
        if self.waiting_for_image:
            # Was waiting, now finish fast
            self.timer.start(30)
        elif self.animation_step < len(self.spiral_path):
            # Speed up to finish
            self.timer.start(30)
        else:
            self.loading_complete.emit()
        
    def stop_animation(self):
        """Stop the animation"""
        self.timer.stop()
        
    def advance_animation(self):
        """Fill the next square in the spiral"""
        if self.animation_step >= len(self.spiral_path):
            # Spiral complete
            self.timer.stop()
            self.loading_complete.emit()
            return
        
        # Add next square in spiral
        self.filled_squares.append(self.spiral_path[self.animation_step])
        self.animation_step += 1
        self.update()
        
        # Near end - slow down and wait for image
        remaining = len(self.spiral_path) - self.animation_step
        if remaining <= 4 and not self.image_ready:
            self.waiting_for_image = True
            self.timer.stop()  # Pause until image ready
        elif self.animation_step >= len(self.spiral_path):
            self.timer.stop()
            if self.image_ready:
                self.loading_complete.emit()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Calculate square size
        w = self.width()
        h = self.height()
        size = min(w, h)
        sq_size = size // self.grid_size
        
        # Center the grid
        offset_x = (w - sq_size * self.grid_size) // 2
        offset_y = (h - sq_size * self.grid_size) // 2
        
        # Draw filled squares with gradient based on order
        for idx, (row, col) in enumerate(self.filled_squares):
            # Color cycles through palette
            color_idx = idx % len(self.colors)
            color = self.colors[color_idx]
            
            # Make recent squares brighter (snake head effect)
            if idx >= len(self.filled_squares) - 3:
                color = QColor("#ffffff")  # White head
            
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            
            x = offset_x + col * sq_size + 3
            y = offset_y + row * sq_size + 3
            painter.drawRoundedRect(x, y, sq_size - 6, sq_size - 6, 8, 8)
        
        painter.end()

# Cache directory for images
CACHE_DIR = Path.home() / ".quote_display" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class QuoteFetcher(QThread):
    """Background thread to fetch quote from Reddit"""
    quote_ready = pyqtSignal(str, str)  # quote, author
    error = pyqtSignal(str)
    
    def run(self):
        log("[QuoteFetch] Starting fetch from Reddit...")
        try:
            # Use Reddit's public JSON API (no auth needed)
            url = "https://www.reddit.com/r/quotes/hot.json?limit=25"
            headers = {'User-Agent': 'QuoteDisplay/1.0'}
            
            response = requests.get(url, headers=headers, timeout=10)
            log(f"[QuoteFetch] Reddit response: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            posts = data['data']['children']
            
            # Collect all valid quotes (skip stickied posts)
            valid_quotes = []
            for post in posts:
                post_data = post['data']
                
                # Skip stickied/pinned posts
                if post_data.get('stickied', False):
                    continue
                
                title = post_data['title']
                
                # Look for quote format (has quotes or dash for attribution)
                if '"' in title or '—' in title or '-' in title or "'" in title:
                    quote, author = self.parse_quote(title)
                    if quote and len(quote) > 10:  # Skip very short titles
                        valid_quotes.append((quote, author))
            
            # Pick a random quote from the valid ones
            if valid_quotes:
                quote, author = random.choice(valid_quotes)
                self.quote_ready.emit(quote, author)
                return
            
            # Fallback: get random non-stickied post
            non_stickied = [p for p in posts if not p['data'].get('stickied', False)]
            if non_stickied:
                post = random.choice(non_stickied)
                title = post['data']['title']
                quote, author = self.parse_quote(title)
                self.quote_ready.emit(quote, author)
                return
            
        except Exception as e:
            log(f"[QuoteFetch] ERROR: {e}")
            self.error.emit(str(e))
    
    def parse_quote(self, text):
        """Extract quote and author from post title"""
        # Common formats:
        # "Quote here" - Author
        # "Quote here" — Author
        # Quote here - Author
        
        # Try to extract quoted text
        quote_match = re.search(r'"([^"]+)"', text)
        if quote_match:
            quote = quote_match.group(1)
            # Look for author after the quote
            remaining = text[quote_match.end():]
            author_match = re.search(r'[-—~]\s*(.+)', remaining)
            author = author_match.group(1).strip() if author_match else "Unknown"
        else:
            # No quotes, try to split on dash
            parts = re.split(r'\s*[-—~]\s*', text, maxsplit=1)
            if len(parts) == 2:
                quote = parts[0].strip()
                author = parts[1].strip()
            else:
                quote = text.strip()
                author = "Unknown"
        
        # Clean up
        quote = quote.strip('"\'')
        author = re.sub(r'\[.*?\]', '', author).strip()  # Remove [tag] markers
        
        return quote, author


class ImageGenerator(QThread):
    """Background thread to generate AI image via Pollinations API"""
    image_ready = pyqtSignal(QPixmap)
    error = pyqtSignal(str)
    
    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
    
    def get_art_prompt(self, quote):
        """Build art prompt from the quote itself"""
        # Clean quote - take first 60 chars, remove special chars
        clean = ''.join(c if c.isalnum() or c == ' ' else ' ' for c in quote[:60])
        clean = ' '.join(clean.split())[:50]
        
        # Add artistic style
        styles = ["oil painting", "digital art", "watercolor", "impressionist", "surreal art"]
        style = random.choice(styles)
        
        return f"{clean} {style}"
    
    def create_fallback_image(self):
        """Create a colorful gradient as fallback"""
        from PIL import Image, ImageDraw
        import hashlib
        
        h = int(hashlib.md5(self.prompt.encode()).hexdigest()[:6], 16)
        r1, g1, b1 = (h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF
        r2, g2, b2 = 255 - r1, 255 - g1, 255 - b1
        
        img = Image.new('RGB', (512, 512))
        draw = ImageDraw.Draw(img)
        
        for y in range(512):
            ratio = y / 512
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            draw.line([(0, y), (512, y)], fill=(r, g, b))
        
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    
    def run(self):
        import time
        
        prompt = self.get_art_prompt(self.prompt)
        styles = ["vibrant", "moody", "dreamy", "cinematic", "ethereal", "bold", "soft", "dramatic"]
        style = random.choice(styles)
        full_prompt = f"{prompt} {style} style"
        
        encoded = urllib.parse.quote(full_prompt)
        seed = int(time.time() * 1000) % 999999
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&seed={seed}&nologo=true"
        
        log(f"[ImageGen] Fetching: {url[:80]}...")
        
        # Try up to 3 times with increasing delays
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = attempt * 5
                    log(f"[ImageGen] Retry {attempt+1}, waiting {wait}s...")
                    time.sleep(wait)
                
                response = requests.get(url, timeout=90)
                log(f"[ImageGen] Status: {response.status_code}, Type: {response.headers.get('Content-Type', 'none')}, Size: {len(response.content)}")
                
                content_type = response.headers.get('Content-Type', '')
                if response.status_code == 200 and 'image' in content_type and len(response.content) > 1000:
                    image = QImage()
                    if image.loadFromData(response.content):
                        log(f"[ImageGen] SUCCESS - image loaded {image.width()}x{image.height()}")
                        self.image_ready.emit(QPixmap.fromImage(image))
                        return
                    else:
                        log("[ImageGen] FAILED - QImage.loadFromData returned False")
                elif response.status_code == 429 or 'Too Many' in response.text:
                    log("[ImageGen] Rate limited, will retry...")
                    continue
                else:
                    log(f"[ImageGen] FAILED - bad response")
                    break
            except requests.exceptions.Timeout:
                log(f"[ImageGen] Timeout on attempt {attempt+1}")
                continue
            except Exception as e:
                log(f"[ImageGen] EXCEPTION: {e}")
                break
        
        # Fallback to gradient
        log("[ImageGen] Using fallback gradient")
        try:
            buffer = self.create_fallback_image()
            image = QImage()
            if image.loadFromData(buffer.read()):
                self.image_ready.emit(QPixmap.fromImage(image))
        except Exception as e:
            log(f"[ImageGen] Fallback also failed: {e}")


class QuoteDisplay(QMainWindow):
    """Main display window"""
    
    def __init__(self):
        super().__init__()
        self.current_quote = ""
        self.current_author = ""
        self.loading = False
        self.loading_frame = 0
        self.loading_chars = ["◐", "◓", "◑", "◒"]
        
        self.setup_ui()
        self.apply_styles()
        
        # Loading animation timer
        self.loading_timer = QTimer()
        self.loading_timer.timeout.connect(self.update_loading_animation)
        
        # Auto-fetch on start
        QTimer.singleShot(500, self.fetch_new_quote)
    
    def update_loading_animation(self):
        """Update loading status text"""
        if self.loading:
            self.loading_frame = (self.loading_frame + 1) % len(self.loading_chars)
            char = self.loading_chars[self.loading_frame]
            # Just update status, squares handle visual animation
            if "Generating" in self.status_label.text() or "Loading" in self.status_label.text():
                pass  # Keep current status message
    
    def start_loading(self):
        """Start the loading animation"""
        self.loading = True
        self.loading_timer.start(200)  # Update every 200ms
    
    def stop_loading(self):
        """Stop the loading animation"""
        self.loading = False
        self.loading_timer.stop()
    
    def setup_ui(self):
        self.setWindowTitle("Quote Display")
        
        main = QWidget()
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Small header
        header = QHBoxLayout()
        
        title = QLabel("Daily Quote")
        title.setObjectName("title")
        header.addWidget(title)
        
        header.addStretch()
        
        # Small refresh button
        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.setFixedSize(70, 70)
        refresh_btn.clicked.connect(self.fetch_new_quote)
        header.addWidget(refresh_btn)
        
        layout.addLayout(header)
        
        # BIG AI Generated Image area (takes most of the screen)
        self.image_frame = QFrame()
        self.image_frame.setObjectName("imageFrame")
        self.image_frame.setMinimumHeight(900)
        self.image_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        image_layout = QVBoxLayout(self.image_frame)
        image_layout.setContentsMargins(10, 10, 10, 10)
        
        # Stacked widget to switch between loading animation and image
        self.image_stack = QStackedWidget()
        
        # Loading animation widget
        self.loading_widget = SquareLoadingWidget()
        self.loading_widget.loading_complete.connect(self.on_loading_animation_done)
        self.image_stack.addWidget(self.loading_widget)
        
        # Image display
        self.image_label = QLabel("")
        self.image_label.setObjectName("imageLabel")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_stack.addWidget(self.image_label)
        
        image_layout.addWidget(self.image_stack)
        
        layout.addWidget(self.image_frame, 3)  # Give image more weight
        
        # Quote display (below image)
        self.quote_label = QLabel("Loading quote...")
        self.quote_label.setObjectName("quoteText")
        self.quote_label.setWordWrap(True)
        self.quote_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.quote_label)
        
        # Author
        self.author_label = QLabel("")
        self.author_label.setObjectName("authorText")
        self.author_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.author_label)
        
        # Status (small)
        self.status_label = QLabel("Fetching from r/quotes...")
        self.status_label.setObjectName("statusText")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)
        
        # Next Quote button
        next_btn = QPushButton("Next Quote →")
        next_btn.setObjectName("nextBtn")
        next_btn.setFixedHeight(80)
        next_btn.clicked.connect(self.fetch_new_quote)
        btn_row.addWidget(next_btn, 3)
        
        # Exit button
        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("exitBtn")
        exit_btn.setFixedHeight(80)
        exit_btn.clicked.connect(self.close)
        btn_row.addWidget(exit_btn, 1)
        
        layout.addLayout(btn_row)
    
    def fetch_new_quote(self):
        """Start fetching a new quote"""
        self.status_label.setText("🔍 Fetching quote from r/quotes...")
        self.quote_label.setText("Loading quote...")
        self.author_label.setText("")
        self.pending_pixmap = None  # Store image while animation plays
        self.image_loaded = False   # Reset success flag
        
        # Show and start loading animation
        self.image_stack.setCurrentIndex(0)
        self.loading_widget.start_animation()
        self.start_loading()
        
        # Stop any old threads
        if hasattr(self, 'quote_thread') and self.quote_thread:
            try:
                self.quote_thread.quote_ready.disconnect()
                self.quote_thread.error.disconnect()
            except:
                pass
        
        self.quote_thread = QuoteFetcher()
        self.quote_thread.quote_ready.connect(self.on_quote_ready)
        self.quote_thread.error.connect(self.on_quote_error)
        self.quote_thread.start()
    
    def on_quote_ready(self, quote, author):
        """Handle received quote"""
        log(f"[Quote] Got quote: {quote[:50]}...")
        self.current_quote = quote
        self.current_author = author
        
        # Update display
        self.quote_label.setText(f'"{quote}"')
        self.author_label.setText(f"— {author}")
        self.status_label.setText("🎨 Generating AI art...")
        
        # Stop any old image thread
        if hasattr(self, 'image_thread') and self.image_thread:
            try:
                self.image_thread.image_ready.disconnect()
                self.image_thread.error.disconnect()
            except:
                pass
        
        # Start image generation
        log("[Quote] Starting ImageGenerator thread...")
        self.image_thread = ImageGenerator(quote)
        self.image_thread.image_ready.connect(self.on_image_ready)
        self.image_thread.error.connect(self.on_image_error)
        self.image_thread.start()
        log("[Quote] Thread started")
    
    def on_quote_error(self, error):
        """Handle quote fetch error"""
        self.stop_loading()
        self.status_label.setText(f"❌ Error: {error}")
        self.quote_label.setText("Could not load quote - tap Next to retry")
        self.image_label.setText("⚠️")
    
    def on_image_ready(self, pixmap):
        """Handle generated image"""
        log(f"[UI] on_image_ready called, pixmap size: {pixmap.width()}x{pixmap.height()}")
        self.image_loaded = True
        self.stop_loading()
        
        # Scale and show immediately
        scaled = pixmap.scaled(
            self.image_frame.width() - 20,
            self.image_frame.height() - 20,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        log(f"[UI] Scaled to: {scaled.width()}x{scaled.height()}")
        
        # Show image directly - skip animation
        self.image_label.setPixmap(scaled)
        self.image_stack.setCurrentIndex(1)
        self.status_label.setText("✅ Loaded!")
        log("[UI] Image set on label")
    
    def on_image_error(self, error):
        """Handle image generation error - should never happen now"""
        # Don't override if we already have an image
        if hasattr(self, 'image_loaded') and self.image_loaded:
            return
        # Just continue - the fallback gradient should have been emitted
        self.stop_loading()
        self.status_label.setText("Tap Next for another quote")
    
    def on_loading_animation_done(self):
        """Called when square animation reaches center"""
        if self.pending_pixmap:
            self.show_pending_image()
        # If image not ready yet, animation just stops and waits
    
    def show_pending_image(self):
        """Display the pending image"""
        if self.pending_pixmap:
            self.image_label.setPixmap(self.pending_pixmap)
            self.image_stack.setCurrentIndex(1)
            self.pending_pixmap = None
    
    def resizeEvent(self, event):
        """Rescale image on resize"""
        super().resizeEvent(event)
        if hasattr(self, 'image_label') and self.image_label.pixmap():
            # Re-scale if we have an image
            pass
    
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #000000;
                color: #ffffff;
                font-family: 'Noto Sans', 'Georgia', serif;
            }
            
            #title {
                font-size: 36px;
                font-weight: bold;
                color: #ffd700;
            }
            
            #refreshBtn {
                background-color: #1a1a2e;
                color: #ffd700;
                border: 2px solid #333355;
                border-radius: 15px;
                font-size: 32px;
            }
            #refreshBtn:pressed {
                background-color: #333355;
            }
            
            #imageFrame {
                background-color: #050510;
                border: 2px solid #222244;
                border-radius: 20px;
            }
            
            #imageLabel {
                font-size: 72px;
                color: #ffd700;
            }
            
            #quoteText {
                font-size: 32px;
                font-style: italic;
                color: #ffffff;
                line-height: 1.3;
                padding: 10px;
            }
            
            #authorText {
                font-size: 26px;
                color: #ffd700;
                font-weight: bold;
            }
            
            #statusText {
                font-size: 18px;
                color: #666688;
            }
            
            #nextBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ffd700, stop:1 #ffaa00);
                color: #000000;
                border: none;
                border-radius: 15px;
                font-size: 28px;
                font-weight: bold;
            }
            #nextBtn:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ccaa00, stop:1 #cc8800);
            }
            
            #exitBtn {
                background-color: #1a0a0a;
                color: #ff6666;
                border: 2px solid #331515;
                border-radius: 15px;
                font-size: 22px;
            }
            #exitBtn:pressed {
                background-color: #331515;
            }
        """)


def main():
    QApplication.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)
    log("[App] Starting Quote Display...")
    app = QApplication(sys.argv)
    app.setFont(QFont("Noto Sans", 14))
    
    log("[App] Creating window...")
    window = QuoteDisplay()
    window.showFullScreen()
    log("[App] Window shown, starting event loop")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

