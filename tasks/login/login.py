from module.base.timer import Timer
from module.exception import GameNotRunningError, WrongAccount
from module.logger import logger
from module.config.utils import deep_get
from module.ocr.ocr import Ocr
from tasks.base.page import page_main
from tasks.base.ui import UI
from tasks.login.assets.assets_login import LOGIN_CHOOSE_ACCOUNT, LOGIN_CONFIRM, LOGIN_LOADING, LOGOUT_COMFIRM, SWITCH_LOGIN, USER_AGREEMENT_ACCEPT, LOGOUT_ACCOUNT_LOGOUT, GAME_INFO
from tasks.login.cloud import LoginAndroidCloud, XPath
from tasks.login.ui import switchAccount


class Login(switchAccount, UI, LoginAndroidCloud):
    
    @property
    def account_info(self):
        return str(deep_get(self.config.data, keys='Login.AccountSwitch.AccountInfo')).replace("*", "")
    
    @property
    def UID(self):
        return str(deep_get(self.config.data, keys='Login.AccountSwitch.GameId'))
    
    @property
    def switch_account(self):
        return deep_get(self.config.data, keys='Login.AccountSwitch.Enable')
    
    @property
    def android_cloud(self):
        return deep_get(self.config.data, keys='Alas.GameClient', default='android') == 'android'

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
        app_timer = Timer(30).start()
        login_success = False
        switched = False
        info = Ocr(button=GAME_INFO)
        
        while 1:
            # End
            # Game client requires at least 5s to start
            # The first few frames might be captured before app_stop(), ignore them
            if startup_timer.reached():
                if self.ui_page_appear(page_main):
                    logger.info('Login to main confirm')
                    break
            
            # Watch if game alive
            if app_timer.reached():
                if not self.device.app_is_running() or ('Android' if self.android_cloud else 'Win') not in info.ocr_single_line(self.device.image).replace('0', 'O'):
                    logger.error('Game died during launch')
                    raise GameNotRunningError('Game not running')
                app_timer.reset()

            # Watch device rotation
            if not login_success and orientation_timer.reached():
                # Screen may rotate after starting an app
                self.device.get_orientation()
                orientation_timer.reset()

            self.device.screenshot()

            # Watch resource downloading and loading
            if self.appear(LOGIN_LOADING, interval=5):
                logger.info('Game resources downloading or loading')
                self.device.stuck_record_clear()
                app_timer.reset()
                orientation_timer.reset()

            # Login directly without switching an account
            if self.appear(LOGIN_CONFIRM) and (not self.switch_account):
                if self.appear_then_click(LOGIN_CONFIRM):
                    login_success = True
                    continue

            # Click Login after choosing
            if switched and not login_success and self.appear(SWITCH_LOGIN):
                if self.appear_then_click(SWITCH_LOGIN):
                    logger.info(f'Login to {self.account_info}')
                    login_success = True
                    continue
            
            # Login after switching an account
            if self.appear(LOGIN_CONFIRM) and self.switch_account and switched:
                if self.appear_then_click(LOGIN_CONFIRM):
                    continue
            
            # Click logout comfirm button
            if self.appear(LOGOUT_COMFIRM) and self.switch_account and not switched:
                if self.appear_then_click(LOGOUT_COMFIRM):
                    logger.info(f'comfirm logout, start changing account')
                    continue
                else:
                    logger.info(f'Failed to click comfirm logout Button')
                    continue
            
            # Click logout button to switch account
            if self.appear(LOGOUT_ACCOUNT_LOGOUT) and self.switch_account and not switched:
                if self.appear_then_click(LOGOUT_ACCOUNT_LOGOUT):
                    logger.info('Logout Button clicked')
                    continue
                else:
                    logger.info('Failed to click logout Button')
                    continue
            
            # Choose account from account list
            if self.appear(LOGIN_CHOOSE_ACCOUNT) and not switched:
                if self.chooseAccount(self.account_info):
                    logger.info(f'Sucessfully switch account to {self.account_info}')
                    switched = True
                    continue
                else:
                    logger.info(f'Failed to switch account to {self.account_info}. Please check whether the account is in the account list')
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

    def checkUID(self, expect: str, button: Ocr): 
        return str(expect) in button.ocr_single_line(self.device.image)

    def ensureAccount(self):
        expectUID = self.UID
        if not self.android_cloud:
            if str(expectUID) in self.xpath(XPath.UID).text:
                return True
            else:
                if self.chooseAccount(expectUID):
                    return True
                else:
                    raise WrongAccount('Wrong Account')
        currentUID = Ocr(button=GAME_INFO) if self.android_cloud else XPath.UID
        ocrTimeout = Timer(5, 1).start()
        while 1:
            if self.checkUID(expect=expectUID, button=currentUID):
                return True
            if ocrTimeout.reached():
                raise GameNotRunningError('Wrong Account')

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

if __name__ == '__main__':
    self = Login('src')
    self.device.screenshot()
    self.handle_app_login()