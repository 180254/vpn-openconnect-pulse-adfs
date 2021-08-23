#!/usr/bin/python3

# required configured python keyring (https://pypi.org/project/keyring/)
# $ keyring set "vpnasdfcreds" "email"    # name.surname@example.com
# $ keyring set "vpnasdfcreds" "password" # password
# $ keyring set "vpnasdfcreds" "totp"     # totpBase32Secret

import argparse
import os
import sys
import time
from distutils.util import strtobool
from typing import Callable, Tuple, Any, Literal, TypeVar, Optional, List
from urllib.parse import urlparse

import keyring
import pyotp
from playwright.sync_api import sync_playwright, Page, Playwright, BrowserContext, Browser

_T = TypeVar('_T')


def require_non_null(value: Optional[_T], name: str) -> _T:
    if value is None:
        raise ValueError(f"{name} must not be null")
    return value


class AppArgs:

    def __init__(self) -> None:
        """AppArgs."""
        super().__init__()
        args_parser = argparse.ArgumentParser()
        args_parser.add_argument("--server", required=True, type=str)
        args_parser.add_argument('--browser', required=True, choices=["chromium", "firefox", "webkit"])
        args_parser.add_argument('--headless', required=True, type=lambda x: bool(strtobool(str(x))))
        args = args_parser.parse_args()

        self.script_basename: str = os.path.splitext(os.path.basename(__file__))[0]
        self.server: str = args.server
        self.browser: Literal["chromium", "firefox", "webkit"] = args.browser
        self.headless: bool = args.headless

        server_parsed = urlparse(self.server)
        self.server_domain: str = server_parsed.netloc


class Credentials:

    def __init__(self) -> None:
        """Credentials."""
        super().__init__()
        self.email: str = require_non_null(keyring.get_password("vpnasdfcreds", "email"), "email")
        self.password: str = require_non_null(keyring.get_password("vpnasdfcreds", "password"), "password")
        self.totp: pyotp.TOTP = pyotp.TOTP(require_non_null(keyring.get_password("vpnasdfcreds", "totp"), "totp"))


class Browser4:

    def __init__(self, app_ags: AppArgs) -> None:
        """Browser4."""
        super().__init__()
        self.default_timeout_seconds: float = 15

        script_dir = os.path.dirname(os.path.realpath(__file__))
        self.state_file: str = os.path.join(script_dir, f"secrets/{app_ags.script_basename}-state.json")
        init_state_file = self.state_file if os.path.exists(self.state_file) else None

        self.playwright: Playwright = sync_playwright().start()
        self.browser: Browser = self.playwright[app_ags.browser].launch(headless=app_ags.headless)
        self.context: BrowserContext = self.browser.new_context(locale="en-US", storage_state=init_state_file)
        self.context.set_default_timeout(self.default_timeout_seconds * 1000)
        self.context.set_default_navigation_timeout(self.default_timeout_seconds * 1000)
        self.page: Page = self.context.new_page()

    def store_session(self):
        self.context.storage_state(path=self.state_file)

    def close(self):
        self.page.close()
        self.context.close()
        self.browser.close()
        self.playwright.stop()


def wait_for_condition(call_id: str,
                       predicate_supplier: Callable[[], bool],
                       timeout_seconds: float,
                       delay_seconds: float,
                       initial_delay_seconds: float,
                       page: Page) -> None:
    condition_ok = False
    attempts_cnt = 0
    attempts_max = timeout_seconds / delay_seconds

    if initial_delay_seconds > 0:
        page.wait_for_timeout(initial_delay_seconds * 1000)
    while not condition_ok and attempts_cnt <= attempts_max:
        try:
            condition_ok = predicate_supplier()
            if not condition_ok:
                print(f"retrying wait_for_condition {call_id}", file=sys.stderr)
                page.wait_for_timeout(delay_seconds * 1000)
                attempts_cnt += 1
        except Exception as e:
            exc_type, _, _ = sys.exc_info()
            # See main() for rationale. There is a similar code.
            if "playwright._impl._api_types.Error" in str(exc_type):
                print(f"retrying wait_for_condition {call_id}, met an exception on the way", file=sys.stderr)
                page.wait_for_timeout(delay_seconds * 1000)
                attempts_cnt += 1
            else:
                raise e
    if not condition_ok:
        raise TimeoutError(f"wait_for_condition {call_id} timed out")


class FixedValuesBackOff:

    def __init__(self, values: List[int]) -> None:
        """FixedValuesBackOffStrategy."""
        super().__init__()
        self.values: List[int] = values
        self.index: int = -1

    def next_back_off(self) -> int:
        self.index += 1
        return self.values[min(self.index, len(self.values) - 1)]

    def reset(self) -> None:
        self.index = -1


class TaskLoop:
    ALL_DONE_COOKIE_FOUND = 0
    TASK_DONE = 1
    EMPTY_MILE = 2
    MFA_FAILED = 3

    def __init__(self, app_args: AppArgs, credentials: Credentials, browser4: Browser4) -> None:
        """EventLoop."""
        super().__init__()
        self.app_args: AppArgs = app_args
        self.credentials: Credentials = credentials
        self.browser4: Browser4 = browser4

    def run_next(self) -> Tuple[int, Any]:
        page = self.browser4.page

        if self.app_args.server_domain in page.url \
                and "No Assertion Received. Please sign in again." in page.content():
            print("VPN Sign-In Page, 'No Assertion Received' error", file=sys.stderr)
            page.click("input[type='submit']")
            return TaskLoop.TASK_DONE, None

        if self.app_args.server_domain in page.url \
                and "Pre Sign-In Notification" in page.content():
            print("VPN Sign-In Page, Pre Sign-In Notification", file=sys.stderr)
            page.click("[name='sn-preauth-proceed']")
            return TaskLoop.TASK_DONE, None

        # Email input is always "visible", but may be off-screen.
        if "login.microsoftonline.com" in page.url \
                and page.is_visible("[name='loginfmt']:not(.moveOffScreen)"):  # msft sso
            print("msft sso, Sign in to your account, Enter email", file=sys.stderr)
            page.fill("[name='loginfmt']", self.credentials.email)
            page.click("input[type='submit']")
            # do not return - continue with password

        if "login.microsoftonline.com" in page.url \
                and page.is_visible("[name='passwd']"):  # msft sso
            print("msft sso, Sign in to your account, Enter password", file=sys.stderr)
            page.fill("[name='passwd']", self.credentials.password)
            page.click("input[type='submit']")
            return TaskLoop.TASK_DONE, None

        if "login.microsoftonline.com" in page.url \
                and page.is_visible("[name='otc']"):  # msft sso
            print("msft sso, Sign in to your account, Enter code", file=sys.stderr)
            page.fill("[name='otc']", self.credentials.totp.now())
            if page.is_enabled("[name='rememberMFA']"):  # yes, may be disabled
                page.check("[name='rememberMFA']")
            page.click("input[type='submit']")

            # This case is too complicated to be solved by the built-in wait_for methods.
            # MFA input will disappear or an invalid code error will appear.
            wait_for_condition(
                "mfa_check_is_ok",
                lambda: (len(page.query_selector_all("[name='otc']")) == 0
                         or len(page.query_selector_all("#idSpan_SAOTCC_Error_OTC")) > 0),
                timeout_seconds=self.browser4.default_timeout_seconds * 1000,
                delay_seconds=0.3,
                # Initial delay may be useful for the invalid code error to be reset. (?)
                initial_delay_seconds=0.3,
                page=page
            )

            mfa_ok = len(page.query_selector_all("[name='otc']")) == 0
            if not mfa_ok:
                # len(page.query_selector_all("#idSpan_SAOTCC_Error_OTC")) > 0 condition is met
                # Sometimes the MFA code is not accepted. I don't know why, it just remains to report the state.
                return TaskLoop.MFA_FAILED, None

            return TaskLoop.TASK_DONE, None

        if "login.microsoftonline.com" in page.url \
                and page.is_visible("[name='DontShowAgain']"):  # msft sso
            print("msft sso, Sign in to your account, Stay signed in?", file=sys.stderr)
            page.check("[name='DontShowAgain']")
            page.click("input[type='submit']")
            return TaskLoop.TASK_DONE, None

        if self.app_args.server_domain in page.url and \
                "You have reached the maximum number of open user sessions" in page.content():
            print("VPN Sign-In Page, Confirmation Open Sessions", file=sys.stderr)
            page.check("[name='postfixSID']")
            page.click("[name='btnContinue']")
            return TaskLoop.TASK_DONE, None

        if self.app_args.server_domain in page.url and \
                "There are already other user sessions in progress" in page.content():
            print("VPN Sign-In Page, Confirmation Open Sessions", file=sys.stderr)
            page.click("[name='btnContinue']")
            return TaskLoop.TASK_DONE, None

        if self.app_args.server_domain in page.url:
            cookies = self.browser4.context.cookies(self.app_args.server)
            cookie = next(filter(lambda c: c["name"] == "DSID", cookies), None)
            if cookie is not None:
                print("reading the DSID cookie", file=sys.stderr)
                payload = f"{cookie['name']}={cookie['value']};"
                return TaskLoop.ALL_DONE_COOKIE_FOUND, payload

        return TaskLoop.EMPTY_MILE, None


def main():
    app_args = AppArgs()
    print(f"{app_args.script_basename} started", file=sys.stderr)

    print("initializing the script, reading credentials", file=sys.stderr)
    credentials = Credentials()

    print("initializing the script, opening the browser", file=sys.stderr)
    browser4 = Browser4(app_args)

    start_time = time.time()
    max_time_seconds = 60

    empty_miles = FixedValuesBackOff([0.2, 0.2, 0.2, 0.4, 0.4, 0.6, 2, 6])

    try:
        browser4.page.goto(app_args.server, wait_until="networkidle")
        task_loop = TaskLoop(app_args, credentials, browser4)

        while True:
            try:
                elapsed_time = time.time() - start_time
                if elapsed_time > max_time_seconds:
                    raise TimeoutError(f"{app_args.script_basename} timed out")

                result, payload = task_loop.run_next()

                if result == TaskLoop.TASK_DONE:
                    empty_miles.reset()
                    browser4.page.wait_for_timeout(timeout=100)

                elif result == TaskLoop.EMPTY_MILE:
                    delay_seconds = empty_miles.next_back_off()
                    print(f"drove an empty mile, pause for {delay_seconds:.1f}s", file=sys.stderr)
                    browser4.page.wait_for_timeout(timeout=delay_seconds * 1000)

                elif result == TaskLoop.MFA_FAILED:
                    print("retrying mfa step, but before that 6 seconds rest", file=sys.stderr)
                    browser4.page.wait_for_timeout(6 * 1000)

                elif result == TaskLoop.ALL_DONE_COOKIE_FOUND:
                    print(payload)  # DSID cookie
                    break

                else:
                    raise AssertionError("unknown TaskLoop result")

            except Exception as e:
                exc_type, _, _ = sys.exc_info()
                # Example exceptions:
                # - Execution context was destroyed, most likely because of a navigation."
                # - Protocol error (Runtime.getProperties): Cannot find context with specified id"
                # These exceptions can occur when a page reload occurs during processing.
                if "playwright._impl._api_types.Error" in str(exc_type):
                    delay_seconds = empty_miles.next_back_off()
                    print(f"drove an exceptionally empty mile, pause for {delay_seconds:.1f}s", file=sys.stderr)
                    browser4.page.wait_for_timeout(timeout=delay_seconds * 1000)
                else:
                    raise e

        print("storing the session", file=sys.stderr)
        browser4.store_session()

    finally:
        browser4.close()
        elapsed_time = time.time() - start_time
        print(f"done, elapsed time {elapsed_time:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
