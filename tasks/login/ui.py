import numpy

from module.base.base import ModuleBase
from tasks.base.ui import UI
from module.base.timer import Timer
from module.base.utils.utils import area_size, random_rectangle_vector_opted
from module.config.utils import deep_get
from module.logger import logger
from module.ocr.ocr import Ocr, OcrResultButton
from module.ocr.keyword import Keyword
from module.ui.draggable_list import DraggableList
from tasks.login.assets.assets_login import LOGIN_CHOOSE_ACCOUNT, CURRENT_ACCOUNT, ACCOUNT_LIST, SWITCH_LOGIN, GAME_INFO

class switchAccount(UI):

    def accountSwtich(self):
        return deep_get((self.config.data, 'Login.AccountSwitch.Enable', False)) if deep_get((self.config.data, 'Login.AccountSwitch.Enable', False)) != None else False

    def dragList(self):
        width, height = area_size(ACCOUNT_LIST.area)
        vector = (0.65, 0.65)
        vector = numpy.random.uniform(*vector)
        vector = (0, vector * height)
        p1, p2 = random_rectangle_vector_opted(vector, box=ACCOUNT_LIST.area)
        self.device.drag(p1, p2, name='ACCOUNT_LIST_DRAG')

    def accountInsight(self, row: str):
        """
        1.OCR + DragList
        2.generate button
        3.select account
        """
        # row = row.replace("*", "")
        accountList = Ocr(button=ACCOUNT_LIST)
        keyword = Keyword(id=1, name='account', cn=row, cht=row, en=row, es=row, jp=row)
        while 1:
            
            results = accountList.matched_ocr(image=self.device.image, keyword_classes=keyword)
            # indexes = [self.keyword2index(row.matched_keyword)
            #        for row in self.cur_buttons]
            # indexes = [index for index in indexes if index]
            if not results:
                self.dragList()
                self.wait_until_stable(button=ACCOUNT_LIST, timer=Timer(0, count=0), timeout=Timer(1.5, count=5))
                continue
            else:
                self.device.click(results[0])
                return True
            
            
        return False

    def chooseAccount(self, accountInfo: str):
        currentAccount = Ocr(button=CURRENT_ACCOUNT)
        if currentAccount.ocr_single_line(self.device.image) == accountInfo:
            return True
        switch = False
        while 1:
            if self.appear(SWITCH_LOGIN) and self.appear(LOGIN_CHOOSE_ACCOUNT):
                self.appear_then_click(LOGIN_CHOOSE_ACCOUNT)
                if self.accountInsight(row=accountInfo):
                    switch = True
            
            if not self.appear(SWITCH_LOGIN) and self.appear(LOGIN_CHOOSE_ACCOUNT) and switch:
                self.appear_then_click(LOGIN_CHOOSE_ACCOUNT)

            if self.appear(SWITCH_LOGIN):
                if currentAccount.ocr_single_line(self.device.image) == accountInfo:
                    return True
                # return False

            # if self.appear_then_click(LOGIN_CHOOSE_ACCOUNT):
            #     logger.info('LOGIN_CHOOSE_ACCOUNT clicked')
            #     self.accountInsight(row=accountInfo)
            # else:
            #     logger.info('Click LOGIN_CHOOSE_ACCOUNT button failed')
            #     continue
        return False
    
    def ensureAccount(self):
        expectUID = deep_get(self.config.data, 'Login.AccountSwitch.GameId', None)
        currentUID = Ocr(button=GAME_INFO)
        ocrTimeout = Timer(5, 1).start()
        while 1:
            if str(expectUID) in currentUID.ocr_single_line(self.device.image):
                return True
            if ocrTimeout.reached():
                return False