from module.logger import logger
from module.base.base import ModuleBase
from tasks.freebies.support_reward import SupportReward
from tasks.login.login import Login

class Freebies(ModuleBase):
    def run(self):
        """
        Run all freebie tasks
        """
        if Login(config=self.config, device=self.device).accountSwtich:
            Login(config=self.config, device=self.device).ensureAccount()
        if self.config.SupportReward_Collect:
            logger.hr('Support Reward')
            SupportReward(config=self.config, device=self.device).run()
            
        self.config.task_delay(server_update=True)