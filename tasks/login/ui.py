from module.base.base import ModuleBase
from tasks.base.ui import UI
from module.logger import logger
from module.ocr.ocr import Ocr, OcrResultButton
from module.ocr.keyword import Keyword
from module.ui.draggable_list import DraggableList
from tasks.login.assets.assets_login import LOGIN_CHOOSE_ACCOUNT, CURRENT_ACCOUNT

class switchAccount(UI):
    def accountInsight(self, row: Keyword):
        accountList = DraggableList('accountList', search_button=LOGIN_CHOOSE_ACCOUNT)
        if accountList.insight_row(row=row, main=self):
            for account in accountList.navigates:
                if account == row:
                    
                    return
        return False

    def chooseAccount(self, accountInfo):
        currentAccount = Ocr(button=CURRENT_ACCOUNT)
        if currentAccount.ocr_single_line == accountInfo:
            return True
        while 1:
            if self.appear_then_click(LOGIN_CHOOSE_ACCOUNT):
                logger.info('LOGIN_CHOOSE_ACCOUNT clicked')
                self.accountInsight(row=accountInfo)
            else:
                logger.info('Click LOGIN_CHOOSE_ACCOUNT button failed')
                continue
        
        return False