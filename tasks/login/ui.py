import numpy

from tasks.base.ui import UI
from module.base.timer import Timer
from module.base.utils.utils import area_size, random_rectangle_vector_opted
from module.config.utils import deep_get
from module.ocr.ocr import Ocr
from module.ocr.keyword import Keyword
from tasks.login.assets.assets_login import LOGIN_CHOOSE_ACCOUNT, CURRENT_ACCOUNT, ACCOUNT_LIST, SWITCH_LOGIN

class switchAccount(UI):

    @property
    def accountSwtich(self):
        return deep_get(self.config.data, 'Login.AccountSwitch.Enable', False)

    def dragList(self):
        width, height = area_size(ACCOUNT_LIST.area)
        vector = (0.7, 0.85)
        vector = numpy.random.uniform(*vector)
        vector = (0, -vector * height)
        p1, p2 = random_rectangle_vector_opted(vector, box=ACCOUNT_LIST.area)
        self.device.drag(p1, p2, name='ACCOUNT_LIST_DRAG')

    def accountInsight(self, row: str):
        """
        row: accountInfo

        1.OCR + DragList
        2.select account
        """
        accountList = Ocr(button=ACCOUNT_LIST)
        keyword = Keyword(id=1, name='account', cn=row, cht=row, en=row, es=row, jp=row)
        while 1:
            
            results = accountList.matched_ocr(image=self.device.image, keyword_classes=keyword)
            if not results:
                self.dragList()
                self.wait_until_stable(button=ACCOUNT_LIST, timer=Timer(0, count=0), timeout=Timer(1.5, count=5))
                continue
            else:
                self.device.click(results[0])
                self.wait_until_stable(button=ACCOUNT_LIST, timer=Timer(0, count=0), timeout=Timer(1.5, count=5))
                return True
            
            
        return False

    def chooseAccount(self, accountInfo: str):
        currentAccount = Ocr(button=CURRENT_ACCOUNT)
        if currentAccount.ocr_single_line(self.device.image) == accountInfo:
            return True
        switch = False
        cnt=0
        while 1:
            if not switch and self.appear(SWITCH_LOGIN) and self.appear(LOGIN_CHOOSE_ACCOUNT):
                self.appear_then_click(LOGIN_CHOOSE_ACCOUNT)
                if self.accountInsight(row=accountInfo):
                    switch = True
            
            if not self.appear(SWITCH_LOGIN) and self.appear(LOGIN_CHOOSE_ACCOUNT) and switch:
                self.appear_then_click(LOGIN_CHOOSE_ACCOUNT)

            if currentAccount.ocr_single_line(self.device.image) == accountInfo and switch:
                return True
            else:
                switch=False
                cnt += 1

            if cnt > 5:
                return False
        return False