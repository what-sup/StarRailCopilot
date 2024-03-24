from module.base.timer import Timer
from module.exception import GameNotRunningError
from module.logger import logger
from tasks.base.page import page_main
from tasks.base.ui import UI
from tasks.login.assets.assets_login import LOGIN_CHOOSE_ACCOUNT, LOGIN_CONFIRM, LOGIN_LOADING, LOGOUT_COMFIRM, SWITCH_LOGIN, USER_AGREEMENT_ACCEPT
from tasks.login.cloud import LoginAndroidCloud, LOGOUT_ACCOUNT_LOGOUT
from tasks.login.ui import switchAccount


class Login(switchAccount, UI, LoginAndroidCloud):
    def _handle_app_login(self):
        """
        Pages:
            in: Any page
            out: page_main

        Raises:
            GameStuckError:
            GameTooManyClickError:
            GameNotRunningError:
        """
        logger.hr('App login')
        orientation_timer = Timer(5)
        startup_timer = Timer(5).start()
        app_timer = Timer(5).start()
        login_success = False
        switch_account = self.config.AccountSwitch_Enable
        switched = False
        
        while 1:
            # Watch if game alive
            if app_timer.reached():
                if not self.device.app_is_running():
                    logger.error('Game died during launch')
                    raise GameNotRunningError('Game not running')
                app_timer.reset()
            # Watch device rotation
            if not login_success and orientation_timer.reached():
                # Screen may rotate after starting an app
                self.device.get_orientation()
                orientation_timer.reset()

            self.device.screenshot()

            # End
            # Game client requires at least 5s to start
            # The first few frames might be captured before app_stop(), ignore them
            if startup_timer.reached():
                if self.ui_page_appear(page_main):
                    logger.info('Login to main confirm')
                    break

            # Watch resource downloading and loading
            if self.appear(LOGIN_LOADING, interval=5):
                logger.info('Game resources downloading or loading')
                self.device.stuck_record_clear()
                app_timer.reset()
                orientation_timer.reset()

            # Login directly without switching an account
            if self.appear(LOGIN_CONFIRM) and not switch_account:
                if self.appear_then_click(LOGIN_CONFIRM):
                    login_success = True
                    continue

            # Login after switching an account
            if self.appear(LOGIN_CONFIRM) and switch_account and switched:
                if self.appear_then_click(LOGIN_CONFIRM):
                    login_success = True
                    continue
            
            # Click logout button to switch account
            if self.appear(LOGOUT_ACCOUNT_LOGOUT) and switch_account:
                if self.appear_then_click(LOGOUT_ACCOUNT_LOGOUT):
                    logger.info('Logout Button clicked');
                    continue
                else:
                    logger.info('Failed to click logout Button')
                    continue

            # Click logout comfirm button
            if self.appear(LOGOUT_COMFIRM) and switch_account:
                if self.appear_then_click():
                    logger.info(f'comfirm logout, start changing account')
                    continue
                else:
                    logger.info(f'Failed to click comfirm logout Button')
                    continue
            
            # Choose account from account list
            if self.appear(LOGIN_CHOOSE_ACCOUNT):
                if self.chooseAccount(self.config.AccountSwitch_AccountInfo):
                    logger.info(f'Sucessfully changed account to {self.config.AccountSwitch_AccountInfo}')
                    switched = True
                    continue
                else:
                    logger.info(f'Failed to switch account to {self.config.AccountSwitch_AccountInfo}. Please check whether the account is in the account list')
                    continue
            
            # Click Login after choosing
            if self.appear(SWITCH_LOGIN) and switched:
                if self.appear_then_click(SWITCH_LOGIN):
                    logger.info(f'Login to {self.config.AccountSwitch_AccountInfo}')
                    continue
                
            if self.appear_then_click(USER_AGREEMENT_ACCEPT):
                continue
            # Additional
            if self.handle_popup_single():
                continue
            if self.handle_popup_confirm():
                continue
            if self.ui_additional():
                continue



        return True

    def handle_app_login(self):
        logger.info('handle_app_login')
        self.device.screenshot_interval_set(1.0)
        self.device.stuck_timer = Timer(300, count=300).start()
        try:
            self._handle_app_login()
        finally:
            self.device.screenshot_interval_set()
            self.device.stuck_timer = Timer(60, count=60).start()

    def app_stop(self):
        logger.hr('App stop')
        self.device.app_stop()

    def app_start(self):
        logger.hr('App start')
        if self.config.is_cloud_game:
            self.cloud_ensure_ingame()
        else:
            self.device.app_start()
        self.handle_app_login()

    def app_restart(self):
        logger.hr('App restart')
        self.device.app_stop()
        if self.config.is_cloud_game:
            self.cloud_ensure_ingame()
        else:
            self.device.app_start()
        self.handle_app_login()
        self.config.task_delay(server_update=True)

    def cloud_start(self):
        if not self.config.is_cloud_game:
            return

        logger.hr('Cloud start')
        self.cloud_ensure_ingame()
        self.handle_app_login()

    def cloud_stop(self):
        if not self.config.is_cloud_game:
            return

        logger.hr('Cloud stop')
        self.app_stop()

    def cloud_start(self):
        if not self.config.is_cloud_game:
            return

        logger.hr('Cloud start')
        self.cloud_ensure_ingame()
        self.handle_app_login()

    def cloud_stop(self):
        if not self.config.is_cloud_game:
            return

        logger.hr('Cloud stop')
        self.app_stop()