import os
import io
import logging
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class CardRenderer:
    """
    Renders ultra-high quality, dark-mode glassmorphic signal infographic cards
    for Telegram VIP channels and Mini App sharing.
    """

    WIDTH = 1200
    HEIGHT = 700

    # Modern Cyberpunk / Dark FinTech color palette
    BG_COLOR = (11, 15, 25)            # Deep Navy / Black
    CARD_BG = (20, 27, 45)             # Glassmorphism container
    CARD_BORDER = (40, 53, 85)
    ACCENT_CYAN = (0, 240, 255)        # Tech glow
    ACCENT_GREEN = (0, 230, 118)       # Bullish
    ACCENT_RED = (255, 61, 87)         # Bearish
    ACCENT_GOLD = (255, 215, 0)        # VIP / XAUUSD
    TEXT_WHITE = (245, 247, 250)
    TEXT_MUTED = (140, 155, 180)
    BADGE_BG = (30, 41, 69)

    def __init__(self):
        self._font_cache = {}

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        cache_key = (size, bold)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        font_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        for path in font_paths:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    self._font_cache[cache_key] = font
                    return font
                except Exception:
                    continue

        # Fallback to default
        font = ImageFont.load_default()
        self._font_cache[cache_key] = font
        return font

    def render_pre_sniper_card(
        self,
        event_title: str,
        bias: str,
        confidence: int,
        current_price: float,
        limit_type: str,
        limit_entry: float,
        limit_sl: float,
        limit_tp: float,
        stop_type: str,
        stop_entry: float,
        stop_sl: float,
        stop_tp: float,
        total_score: float,
        symbol: str = "XAUUSD (GOLD)",
    ) -> io.BytesIO:
        """
        Creates the 4:58 Pre-Sniper Telegram VIP infographic card.
        """
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), color=self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        is_bullish = "BULLISH" in bias or "BUY" in bias
        theme_color = self.ACCENT_GREEN if is_bullish else self.ACCENT_RED

        # 1. Subtle Background Gradients & Glow accents
        draw.rectangle([(20, 20), (self.WIDTH - 20, self.HEIGHT - 20)], fill=self.CARD_BG, outline=self.CARD_BORDER, width=2)
        
        # Top banner glow bar
        draw.rectangle([(20, 20), (self.WIDTH - 20, 28)], fill=theme_color)

        # 2. Header: Logo, Event & Symbol
        font_title = self._get_font(34, bold=True)
        font_sub = self._get_font(20, bold=False)
        font_badge = self._get_font(18, bold=True)

        draw.text((50, 48), "MACRO SNIPER AI", font=font_title, fill=self.ACCENT_CYAN)
        draw.text((50, 92), f"HIGH-IMPACT NEWS EXECUTION • {symbol}", font=font_sub, fill=self.TEXT_MUTED)

        # Event Badge (Right)
        badge_text = "TIER-1 RED FOLDER"
        draw.rounded_rectangle([(self.WIDTH - 260, 48), (self.WIDTH - 50, 92)], radius=8, fill=self.BADGE_BG, outline=self.ACCENT_RED, width=1)
        draw.text((self.WIDTH - 240, 58), badge_text, font=font_badge, fill=self.ACCENT_RED)

        # Event Headline
        font_event = self._get_font(26, bold=True)
        draw.text((50, 135), f"EVENT: {event_title.upper()}", font=font_event, fill=self.TEXT_WHITE)

        # Divider line
        draw.line([(50, 180), (self.WIDTH - 50, 180)], fill=self.CARD_BORDER, width=1)

        # 3. Macro Bias & Confidence Section
        # Bias Box
        draw.rounded_rectangle([(50, 205), (420, 310)], radius=12, fill=(26, 35, 60), outline=theme_color, width=2)
        font_label = self._get_font(16, bold=True)
        font_bias = self._get_font(28, bold=True)
        draw.text((70, 220), "AI MACRO PREDICTION", font=font_label, fill=self.TEXT_MUTED)
        draw.text((70, 250), bias, font=font_bias, fill=theme_color)

        # Confidence & Score Box
        draw.rounded_rectangle([(440, 205), (780, 310)], radius=12, fill=(26, 35, 60), outline=self.CARD_BORDER, width=1)
        draw.text((460, 220), "CONFIDENCE & SCORE", font=font_label, fill=self.TEXT_MUTED)
        draw.text((460, 250), f"{confidence}%", font=font_bias, fill=self.TEXT_WHITE)
        draw.text((560, 255), f"S_total: {total_score:+0.1f}", font=self._get_font(22, bold=True), fill=self.ACCENT_CYAN)

        # Current Price Box
        draw.rounded_rectangle([(800, 205), (self.WIDTH - 50, 310)], radius=12, fill=(26, 35, 60), outline=self.CARD_BORDER, width=1)
        draw.text((820, 220), "T-2M REFERENCE PRICE", font=font_label, fill=self.TEXT_MUTED)
        draw.text((820, 250), f"{current_price:.2f}", font=font_bias, fill=self.ACCENT_GOLD)

        # 4. ORDER MATRICES: 1) Judas Swing Limit Trap, 2) Momentum Breakout
        # Matrix 1: Judas Swing Limit Trap (The Secret Sauce)
        draw.rounded_rectangle([(50, 335), (580, 580)], radius=14, fill=(22, 31, 55), outline=self.ACCENT_GOLD, width=2)
        draw.text((70, 355), "🎯 ORDER 1: JUDAS SWING TRAP (LIMIT)", font=self._get_font(20, bold=True), fill=self.ACCENT_GOLD)
        draw.text((70, 385), "Catches the initial market-maker fake spike liquidity sweep", font=self._get_font(14), fill=self.TEXT_MUTED)

        font_order_type = self._get_font(24, bold=True)
        draw.text((70, 425), f"TYPE: {limit_type}", font=font_order_type, fill=theme_color)
        draw.text((70, 465), f"ENTRY:  {limit_entry:.2f}", font=font_order_type, fill=self.TEXT_WHITE)
        draw.text((70, 505), f"STOP-LOSS:   {limit_sl:.2f}", font=font_order_type, fill=self.ACCENT_RED)
        draw.text((70, 540), f"TAKE-PROFIT: {limit_tp:.2f}  (+1200 pts)", font=font_order_type, fill=self.ACCENT_GREEN)

        # Matrix 2: Momentum Breakout Stop Order
        draw.rounded_rectangle([(620, 335), (self.WIDTH - 50, 580)], radius=14, fill=(22, 31, 55), outline=self.CARD_BORDER, width=1)
        draw.text((640, 355), "⚡ ORDER 2: MOMENTUM BREAKOUT (STOP)", font=self._get_font(20, bold=True), fill=self.ACCENT_CYAN)
        draw.text((640, 385), "Executes if price explodes immediately without fake-out", font=self._get_font(14), fill=self.TEXT_MUTED)

        draw.text((640, 425), f"TYPE: {stop_type}", font=font_order_type, fill=theme_color)
        draw.text((640, 465), f"ENTRY:  {stop_entry:.2f}", font=font_order_type, fill=self.TEXT_WHITE)
        draw.text((640, 505), f"STOP-LOSS:   {stop_sl:.2f}", font=font_order_type, fill=self.ACCENT_RED)
        draw.text((640, 540), f"TAKE-PROFIT: {stop_tp:.2f}  (+1000 pts)", font=font_order_type, fill=self.ACCENT_GREEN)

        # 5. Footer Security & Latency Guarantee
        draw.line([(50, 610), (self.WIDTH - 50, 610)], fill=self.CARD_BORDER, width=1)
        draw.text((50, 630), "⚡ Ultra-Fast 5:00:01 Kill-Switch Guard Active • MT5 Bridge Connected", font=font_sub, fill=self.ACCENT_CYAN)
        draw.text((self.WIDTH - 300, 630), "Aether MacroSniper SaaS", font=font_sub, fill=self.TEXT_MUTED)

        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output

    def render_safety_alert_card(
        self,
        event_title: str,
        is_confirmed: bool,
        actual: float,
        forecast: float,
        headline: str,
        action_message: str,
        symbol: str = "XAUUSD",
    ) -> io.BytesIO:
        """
        Creates the 5:00:01 Instant Verification or Kill-Switch card.
        """
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), color=self.BG_COLOR)
        draw = ImageDraw.Draw(img)

        theme_color = self.ACCENT_GREEN if is_confirmed else self.ACCENT_RED

        # Glass container & Glowing border
        draw.rectangle([(20, 20), (self.WIDTH - 20, self.HEIGHT - 20)], fill=self.CARD_BG, outline=theme_color, width=3)
        draw.rectangle([(20, 20), (self.WIDTH - 20, 28)], fill=theme_color)

        font_header = self._get_font(32, bold=True)
        font_sub = self._get_font(20, bold=False)
        font_giant = self._get_font(40, bold=True)
        font_val = self._get_font(28, bold=True)

        draw.text((50, 48), "MACRO SNIPER AI • 5:00:01 INSTANT VERIFICATION", font=font_header, fill=self.ACCENT_CYAN)
        draw.text((50, 92), f"SYMBOL: {symbol} • {event_title.upper()}", font=font_sub, fill=self.TEXT_MUTED)

        # Headline Banner
        banner_bg = (20, 45, 30) if is_confirmed else (50, 20, 30)
        draw.rounded_rectangle([(50, 140), (self.WIDTH - 50, 250)], radius=14, fill=banner_bg, outline=theme_color, width=2)
        draw.text((70, 175), headline, font=font_giant, fill=theme_color)

        # Actual vs Forecast comparison boxes
        # Box 1: Actual Released
        draw.rounded_rectangle([(50, 280), (380, 420)], radius=12, fill=(26, 35, 60), outline=theme_color, width=2)
        draw.text((70, 300), "ACTUAL RELEASED", font=self._get_font(18, bold=True), fill=self.TEXT_MUTED)
        draw.text((70, 340), f"{actual}", font=self._get_font(42, bold=True), fill=theme_color)

        # Box 2: Forecast
        draw.rounded_rectangle([(410, 280), (740, 420)], radius=12, fill=(26, 35, 60), outline=self.CARD_BORDER, width=1)
        draw.text((430, 300), "FORECAST ESTIMATE", font=self._get_font(18, bold=True), fill=self.TEXT_MUTED)
        draw.text((430, 340), f"{forecast}", font=self._get_font(42, bold=True), fill=self.TEXT_WHITE)

        # Box 3: Deviation
        dev = round(actual - forecast, 3)
        draw.rounded_rectangle([(770, 280), (self.WIDTH - 50, 420)], radius=12, fill=(26, 35, 60), outline=self.CARD_BORDER, width=1)
        draw.text((790, 300), "SURPRISE DEVIATION", font=self._get_font(18, bold=True), fill=self.TEXT_MUTED)
        draw.text((790, 340), f"{dev:+0.2f}", font=self._get_font(42, bold=True), fill=self.ACCENT_CYAN)

        # Action instructions box
        draw.rounded_rectangle([(50, 450), (self.WIDTH - 50, 600)], radius=14, fill=(22, 31, 55), outline=self.CARD_BORDER, width=1)
        draw.text((70, 470), "⚡ ALGORITHMIC ACTION DIRECTIVE:", font=self._get_font(20, bold=True), fill=self.ACCENT_GOLD)
        
        # Word wrap or lines for action message
        draw.text((70, 515), action_message, font=font_val, fill=self.TEXT_WHITE)

        # Footer
        draw.line([(50, 630), (self.WIDTH - 50, 630)], fill=self.CARD_BORDER, width=1)
        draw.text((50, 645), "Execution Latency: < 0.3s • Direct MT5 Zero-Slip Broker Bridge", font=font_sub, fill=self.TEXT_MUTED)

        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output


card_renderer = CardRenderer()
