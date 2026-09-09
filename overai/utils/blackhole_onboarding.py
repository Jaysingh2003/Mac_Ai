"""
BlackHole Audio Onboarding — shown once to set up system audio capture.
Guides the user to install BlackHole (free virtual audio driver) so OverAI
can capture both mic + system audio (YouTube, Spotify, etc.) simultaneously.
"""

import subprocess
import threading
import objc
from pathlib import Path

from Foundation import NSObject, NSMakeRect, NSTimer, NSURL, NSUserDefaults
from AppKit import (
    NSWindow, NSView, NSButton, NSTextField, NSImageView,
    NSColor, NSFont, NSImage, NSVisualEffectView,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSBackingStoreBuffered, NSTextAlignmentCenter,
    NSVisualEffectMaterialWindowBackground,
    NSApp, NSWorkspace, NSBezelStyleRounded,
    NSViewWidthSizable, NSViewMinYMargin, NSViewMaxYMargin,
    NSScreen
)

from .logger import Logger

logger = Logger("BlackHoleOnboarding")

BLACKHOLE_DOWNLOAD_URL = "https://existential.audio/blackhole/"
BLACKHOLE_SKIPPED_KEY = "com.overai.blackholeOnboardingSkipped"
BLACKHOLE_DONE_KEY = "com.overai.blackholeSetupDone"


def is_blackhole_installed() -> bool:
    """Check if BlackHole virtual audio driver is installed."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPAudioDataType"],
            capture_output=True, text=True, timeout=5
        )
        return "BlackHole" in result.stdout
    except Exception:
        return False


def should_show_blackhole_onboarding() -> bool:
    """Return True if we should show the BlackHole setup guide."""
    defaults = NSUserDefaults.standardUserDefaults()
    if defaults.boolForKey_(BLACKHOLE_DONE_KEY):
        return False
    if defaults.boolForKey_(BLACKHOLE_SKIPPED_KEY):
        return False
    if is_blackhole_installed():
        # Already installed — mark done silently
        defaults.setBool_forKey_(True, BLACKHOLE_DONE_KEY)
        return False
    return True


def mark_blackhole_done():
    defaults = NSUserDefaults.standardUserDefaults()
    defaults.setBool_forKey_(True, BLACKHOLE_DONE_KEY)
    defaults.synchronize()


# ---------------------------------------------------------------------------
# Delegate / handler helpers
# ---------------------------------------------------------------------------

class _BHDelegate(NSObject):
    parent = objc.ivar()

    def windowWillClose_(self, notification):
        if self.parent:
            self.parent._on_close()


class _BHTimerHandler(NSObject):
    parent = objc.ivar()

    def checkInstall_(self, timer):
        if self.parent:
            self.parent._check_installed()


class _BHButtonHandler(NSObject):
    parent = objc.ivar()

    def downloadClicked_(self, sender):
        if self.parent:
            self.parent._open_download()

    def skipClicked_(self, sender):
        if self.parent:
            self.parent._skip()

    def doneClicked_(self, sender):
        if self.parent:
            self.parent._done()


# ---------------------------------------------------------------------------
# Main onboarding window
# ---------------------------------------------------------------------------

class BlackHoleOnboardingWindow:

    W = 500
    H = 520

    def __init__(self):
        self.window = None
        self._callback = None
        self._timer = None
        self._status_label = None
        self._done_btn = None
        self._download_btn = None

        self._delegate = _BHDelegate.alloc().init()
        self._delegate.parent = self

        self._timer_handler = _BHTimerHandler.alloc().init()
        self._timer_handler.parent = self

        self._btn_handler = _BHButtonHandler.alloc().init()
        self._btn_handler.parent = self

    def show(self, callback):
        self._callback = callback
        self._build_window()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        self._start_polling()

    def _build_window(self):
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - self.W) / 2
        y = (screen.size.height - self.H) / 2

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, self.W, self.H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False
        )
        self.window.setTitle_("OverAI — System Audio Setup")
        self.window.setDelegate_(self._delegate)

        cv = self.window.contentView()
        cv.setWantsLayer_(True)

        # Background blur
        bg = NSVisualEffectView.alloc().initWithFrame_(cv.bounds())
        bg.setMaterial_(NSVisualEffectMaterialWindowBackground)
        bg.setBlendingMode_(0)
        bg.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin | NSViewMaxYMargin)
        cv.addSubview_(bg)

        self._add_icon(cv)
        self._add_title(cv)
        self._add_steps(cv)
        self._add_status(cv)
        self._add_buttons(cv)

    def _add_icon(self, parent):
        iv = NSImageView.alloc().initWithFrame_(
            NSMakeRect((self.W - 72) / 2, self.H - 110, 72, 72)
        )
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "waveform.circle.fill", "Audio"
        )
        if img:
            iv.setImage_(img)
            iv.setContentTintColor_(NSColor.systemBlueColor())
        parent.addSubview_(iv)

    def _add_title(self, parent):
        t = self._label(
            "Enable System Audio Capture",
            NSMakeRect(30, self.H - 150, self.W - 60, 28),
            NSFont.boldSystemFontOfSize_(18),
            NSColor.labelColor()
        )
        t.setAlignment_(NSTextAlignmentCenter)
        parent.addSubview_(t)

        sub = self._label(
            "Record mic + YouTube + any app audio simultaneously",
            NSMakeRect(30, self.H - 178, self.W - 60, 20),
            NSFont.systemFontOfSize_(13),
            NSColor.secondaryLabelColor()
        )
        sub.setAlignment_(NSTextAlignmentCenter)
        parent.addSubview_(sub)

    def _add_steps(self, parent):
        steps = [
            ("1", "Install Homebrew (if not already installed)",
             "Open Terminal and run: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""),
            ("2", "Download & install BlackHole 2ch",
             "Free virtual audio driver — click 'Download BlackHole' below"),
            ("3", "Install SwitchAudioSource (auto-switching)",
             "In Terminal run: brew install switchaudio-osx"),
            ("4", "Done! OverAI auto-detects and uses both mic + system audio",
             "No manual switching needed — OverAI handles it automatically"),
        ]

        y = self.H - 310
        for num, title, detail in steps:
            # Circle number
            circle = self._label(
                num,
                NSMakeRect(30, y, 28, 28),
                NSFont.boldSystemFontOfSize_(13),
                NSColor.whiteColor()
            )
            circle.setAlignment_(NSTextAlignmentCenter)
            circle.setWantsLayer_(True)
            circle.layer().setBackgroundColor_(NSColor.systemBlueColor().CGColor())
            circle.layer().setCornerRadius_(14)
            parent.addSubview_(circle)

            # Step title
            tl = self._label(
                title,
                NSMakeRect(68, y + 8, self.W - 98, 18),
                NSFont.systemFontOfSize_(13),
                NSColor.labelColor()
            )
            parent.addSubview_(tl)

            # Step detail
            dl = self._label(
                detail,
                NSMakeRect(68, y - 8, self.W - 98, 16),
                NSFont.systemFontOfSize_(11),
                NSColor.secondaryLabelColor()
            )
            parent.addSubview_(dl)

            y -= 58

    def _add_status(self, parent):
        self._status_label = self._label(
            "⏳ Waiting for BlackHole installation...",
            NSMakeRect(30, 100, self.W - 60, 22),
            NSFont.systemFontOfSize_(12),
            NSColor.secondaryLabelColor()
        )
        self._status_label.setAlignment_(NSTextAlignmentCenter)
        parent.addSubview_(self._status_label)

    def _add_buttons(self, parent):
        bw, bh = 160, 32
        gap = 16
        total = bw * 3 + gap * 2
        sx = (self.W - total) / 2
        y = 48

        # Download button (primary)
        self._download_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(sx, y, bw, bh)
        )
        self._download_btn.setTitle_("Download BlackHole")
        self._download_btn.setBezelStyle_(NSBezelStyleRounded)
        self._download_btn.setTarget_(self._btn_handler)
        self._download_btn.setAction_("downloadClicked:")
        self._download_btn.setKeyEquivalent_("\r")
        parent.addSubview_(self._download_btn)

        # Done button (disabled until detected)
        self._done_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(sx + bw + gap, y, bw, bh)
        )
        self._done_btn.setTitle_("I've Installed It ✓")
        self._done_btn.setBezelStyle_(NSBezelStyleRounded)
        self._done_btn.setTarget_(self._btn_handler)
        self._done_btn.setAction_("doneClicked:")
        self._done_btn.setEnabled_(False)
        parent.addSubview_(self._done_btn)

        # Skip button
        skip = NSButton.alloc().initWithFrame_(
            NSMakeRect(sx + (bw + gap) * 2, y, bw, bh)
        )
        skip.setTitle_("Skip for Now")
        skip.setBezelStyle_(NSBezelStyleRounded)
        skip.setTarget_(self._btn_handler)
        skip.setAction_("skipClicked:")
        parent.addSubview_(skip)

    # ------------------------------------------------------------------

    def _label(self, text, frame, font, color):
        f = NSTextField.alloc().initWithFrame_(frame)
        f.setStringValue_(text)
        f.setBezeled_(False)
        f.setDrawsBackground_(False)
        f.setEditable_(False)
        f.setSelectable_(False)
        f.setFont_(font)
        f.setTextColor_(color)
        return f

    def _start_polling(self):
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.5, self._timer_handler, "checkInstall:", None, True
        )

    def _check_installed(self):
        if is_blackhole_installed():
            self._status_label.setStringValue_("✅ BlackHole detected! Click 'I've Installed It'")
            self._status_label.setTextColor_(NSColor.systemGreenColor())
            self._done_btn.setEnabled_(True)
            self._done_btn.setKeyEquivalent_("\r")
            self._download_btn.setKeyEquivalent_("")
            if self._timer:
                self._timer.invalidate()
                self._timer = None

    def _open_download(self):
        url = NSURL.URLWithString_(BLACKHOLE_DOWNLOAD_URL)
        NSWorkspace.sharedWorkspace().openURL_(url)
        self._status_label.setStringValue_("🌐 Browser opened — install BlackHole 2ch, then return here")
        self._status_label.setTextColor_(NSColor.systemOrangeColor())

    def _done(self):
        mark_blackhole_done()
        self._close()
        if self._callback:
            self._callback(True)

    def _skip(self):
        defaults = NSUserDefaults.standardUserDefaults()
        defaults.setBool_forKey_(True, BLACKHOLE_SKIPPED_KEY)
        defaults.synchronize()
        self._close()
        if self._callback:
            self._callback(False)

    def _on_close(self):
        self._close()
        if self._callback:
            self._callback(False)

    def _close(self):
        if self._timer:
            self._timer.invalidate()
            self._timer = None
        if self.window:
            self.window.close()
            self.window = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_blackhole_onboarding(callback):
    """Show BlackHole setup guide. callback(success: bool)."""
    win = BlackHoleOnboardingWindow()
    win.show(callback)
    return win
