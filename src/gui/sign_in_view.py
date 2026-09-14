"""sign_in_view.py -- the embedded view a venue's own desktop sign-in is approved in.

``SignInView`` opens for one sign-in and answers the address it landed on, and
``SignInPage`` reaches only the two addresses that sign-in was given.
``open_sign_in_view`` is the callable ``ata_spm_signin.SignInSession.view``
takes. ``sign_in_session`` binds it to ``ata_spm_signin.default_session``,
which ``market_inspector`` and ``react_market_inspector_tab`` each hand
``AtaSpmSettings.set_connector``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..trading import ata_spm_signin

try:
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QDialog, QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine no class below is defined and open_sign_in_view raises.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.sign_in_view")

WINDOW_TITLE = "Venue sign-in"
ACCESSIBLE_NAME = "Venue sign-in view"
ACCESSIBLE_DESCRIPTION = (
    "Approve the venue here. The window closes by itself once the venue answers."
)
VIEW_ACCESSIBLE_NAME = "Venue sign-in page"
VIEW_ACCESSIBLE_DESCRIPTION = "The venue's own sign-in page, and nothing else."

VIEW_WIDTH_PX = 540
VIEW_HEIGHT_PX = 760

MILLISECONDS_PER_SECOND = 1000

NO_ADDRESS = ""

#: What one sign-in ended by, and the whole of what its log line carries. No
#: wording here names an address, which is where a venue puts its token.
LANDED_REASON = "the venue answered at its published redirect"
CANCELLED_REASON = "the operator closed the view"
TIMED_OUT_REASON = "the wait ran out"
LEFT_VENUE_FORMAT = "the view reached {host}, which this sign-in was not sent to"

OPENED_LOG = "ATA-SPM sign-in view opened on %s"
CLOSED_LOG = "ATA-SPM sign-in view closed: %s"

NO_WEBENGINE_TEXT = (
    "this build draws no web view, and this venue answers only inside one"
)


if _HAS_WEBENGINE:

    class SignInPage(QWebEnginePage):
        """The page of one ``SignInView``, reaching two addresses and no more.

        ``acceptNavigationRequest`` hands every address to ``SignInView.reach``,
        and ``createWindow`` answers None.
        """

        def __init__(self, profile: Any, view: Any) -> None:
            super().__init__(profile, view)
            self._view = view

        def acceptNavigationRequest(
            self, url: Any, kind: Any, is_main_frame: bool
        ) -> bool:
            """Answer whether ``SignInView.reach`` lets the view load one address."""
            del kind, is_main_frame
            return bool(self._view.reach(url.toString()))

        def createWindow(self, kind: Any) -> Any:
            """Answer None, which opens no second view beside ``SignInPage``."""
            del kind
            return None

    class SignInView(QDialog):
        """One venue's sign-in, open only while that sign-in is in flight.

        ``run`` shows the view on the approval address and answers the address
        it landed on, or ``NO_ADDRESS``.
        """

        def __init__(
            self,
            authorize_url: Any,
            redirect_address: Any,
            timeout: float,
            parent: Optional[Any] = None,
        ) -> None:
            super().__init__(parent)
            self._authorize_url = str(authorize_url)
            self._redirect = str(redirect_address)
            self._hosts = ata_spm_signin.sign_in_hosts(authorize_url, redirect_address)
            self._landed = NO_ADDRESS
            self._ended = False
            self.setWindowTitle(WINDOW_TITLE)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setAccessibleDescription(ACCESSIBLE_DESCRIPTION)
            self.setModal(True)
            self.setFixedSize(VIEW_WIDTH_PX, VIEW_HEIGHT_PX)

            column = QVBoxLayout(self)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            self._profile = QWebEngineProfile()
            self._profile.downloadRequested.connect(self._refuse_download)
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(VIEW_ACCESSIBLE_NAME)
            self._web.setAccessibleDescription(VIEW_ACCESSIBLE_DESCRIPTION)
            self._web.setContextMenuPolicy(Qt.NoContextMenu)
            self._page = SignInPage(self._profile, self)
            self._web.setPage(self._page)
            column.addWidget(self._web, 1)

            self._clock = QTimer(self)
            self._clock.setSingleShot(True)
            self._clock.timeout.connect(self._on_timeout)
            self._clock.start(int(float(timeout) * MILLISECONDS_PER_SECOND))

        def reach(self, address: Any) -> bool:
            """Answer whether the view may load one address, ending the sign-in where it leaves.

            ``is_redirect_landing`` takes the published redirect and refuses it,
            and an address naming no host is refused without ending the sign-in.
            """
            held = str(address)
            if ata_spm_signin.is_redirect_landing(held, self._redirect):
                self._landed = held
                self._end(LANDED_REASON)
                return False
            host = ata_spm_signin.landed_host(held)
            if not host:
                return False
            if host in self._hosts:
                return True
            self._end(LEFT_VENUE_FORMAT.format(host=host))
            return False

        def run(self) -> str:
            """Show the view until it ends, and answer the address it landed on."""
            logger.debug(OPENED_LOG, ata_spm_signin.landed_host(self._authorize_url))
            self._web.setUrl(QUrl(self._authorize_url))
            self.exec()
            self._release()
            return self._landed

        def closeEvent(self, event: Any) -> None:
            """End the sign-in where the operator closes ``SignInView``."""
            if not self._ended:
                self._end(CANCELLED_REASON)
            super().closeEvent(event)

        def reject(self) -> None:
            """End the sign-in where the operator cancels ``SignInView``."""
            if not self._ended:
                self._end(CANCELLED_REASON)
            super().reject()

        def _on_timeout(self) -> None:
            """End the sign-in with ``NO_ADDRESS`` once ``_clock`` runs out."""
            self._landed = NO_ADDRESS
            self._end(TIMED_OUT_REASON)

        def _end(self, reason: str) -> None:
            """Close ``SignInView`` once, recording only ``reason``."""
            if self._ended:
                return
            self._ended = True
            self._clock.stop()
            logger.debug(CLOSED_LOG, reason)
            QTimer.singleShot(0, self.accept)

        def _refuse_download(self, item: Any) -> None:
            """Cancel one download ``_profile`` reports, which writes no file."""
            item.cancel()

        def _release(self) -> None:
            """Empty the cookie jar of ``_profile`` and drop ``_page``.

            ``SignInView.run`` calls it once ``exec`` has returned.
            """
            self._profile.cookieStore().deleteAllCookies()
            self._web.stop()
            self._page.deleteLater()
            self._web.deleteLater()


def open_sign_in_view(authorize_url: Any, redirect_address: Any) -> str:
    """Approve one sign-in in a ``SignInView`` and answer the address it landed on.

    ``ata_spm_signin.CALLBACK_TIMEOUT_SECONDS`` is the wait, and a build
    without ``_HAS_WEBENGINE`` raises ``NO_WEBENGINE_TEXT``.
    """
    if not _HAS_WEBENGINE:
        raise ata_spm_signin.SignInError(NO_WEBENGINE_TEXT)
    return SignInView(
        authorize_url,
        redirect_address,
        ata_spm_signin.CALLBACK_TIMEOUT_SECONDS,
    ).run()


def sign_in_session() -> Any:
    """``ata_spm_signin.default_session`` with ``open_sign_in_view`` wired to it.

    ``MarketInspectorTab`` and ``MarketInspectorReactTab`` each hand this to
    ``ata_spm_signin.build_connector``.
    """
    return ata_spm_signin.default_session(view=open_sign_in_view)
