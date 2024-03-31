from datetime import datetime, timedelta

from module.logger import logger
from module.exception import GameNotRunningError
from tasks.assignment.claim import AssignmentClaim
from tasks.assignment.keywords import (AssignmentEntry, AssignmentEventGroup, KEYWORDS_ASSIGNMENT_GROUP)
from tasks.assignment.ui import AssignmentStatus
from tasks.base.page import page_assignment, page_menu
from tasks.daily.keywords import KEYWORDS_DAILY_QUEST
from tasks.daily.synthesize import SynthesizeUI
from tasks.login.ui import switchAccount


class Assignment(AssignmentClaim, SynthesizeUI):
    def run(self, assignments: list[AssignmentEntry] = None, duration: int = None, event_first: bool = None):
        if switchAccount.accountSwtich:
            if not switchAccount.ensureAccount(self):
                raise GameNotRunningError('Game not running')

        now = datetime.now()
        self.config.update_battle_pass_quests()
        self.config.update_daily_quests()
        
        if assignments is None:
            assignments = (
                getattr(self.config, f'Assignment_Name_{i + 1}', None) for i in range(4))
            # remove duplicate while keeping order
            assignments = list(dict.fromkeys(
                x for x in assignments if x is not None))
            assignments = [AssignmentEntry.find(x) for x in assignments]
            if len(assignments) < 4:
                logger.warning(
                    'There are duplicate assignments in config, check it out')
        if duration is None:
            duration = self.config.Assignment_Duration
        if event_first is None:
            event_first = self.config.Assignment_Event

        configDuration = duration
        if duration == 24: 
            duration = 20

        self.dispatched = dict()
        self.has_new_dispatch = False
        self.ensure_scroll_top(page_menu)
        self.ui_ensure(page_assignment)
        event_ongoing = next((
            g for g in self._iter_groups()
            if isinstance(g, AssignmentEventGroup)
        ), None)
        if event_first and event_ongoing is not None:
            undispatched = assignments
            remain = self._check_all()
            remain = self._dispatch_event(remain)
        else:
            # Iterate in user-specified order, return undispatched ones
            undispatched = list(self._check_inlist(assignments, duration))
            remain = self._check_all()
        undispatched = [x for x in undispatched if x not in self.dispatched]
        # There are unchecked assignments
        if remain > 0:
            for assignment in undispatched[:remain]:
                self.goto_entry(assignment)
                self.dispatch(assignment, duration)
            if remain < len(undispatched):
                logger.warning('The following assignments can not be dispatched due to limit: '
                               f'{", ".join([x.name for x in undispatched[remain:]])}')
            elif remain > len(undispatched):
                self._dispatch_remain(duration, remain - len(undispatched))
        # Refresh dashboard before return
        _ = self._limit_status
        # Scheduler
        logger.attr('has_new_dispatch', self.has_new_dispatch)
        with self.config.multi_set():
            # Check daily
            quests = self.config.stored.DailyQuest.load_quests()
            if KEYWORDS_DAILY_QUEST.Dispatch_1_assignments in quests:
                logger.info('Achieved daily quest Dispatch_1_assignments')
                self.config.task_call('DailyQuest')
            # Delay self
            if len(self.dispatched):
                delay = min(self.dispatched.values())
                if configDuration == 24:
                    delay = now + timedelta(hours=24)
                logger.info(f'Delay assignment check to {str(delay)}')
                self.config.task_delay(target=delay)
            else:
                # ValueError: min() arg is an empty sequence
                logger.error('Empty dispatched list, delay 2 hours instead')
                self.config.task_delay(minute=120)

    def _check_inlist(self, assignments: list[AssignmentEntry], duration: int):
        """
        Dispatch assignments according to user config

        Args:
            assignments (list[AssignmentEntry]): user specified assignments
            duration (int): user specified duration
        """
        if not assignments:
            return
        logger.hr('Assignment check inlist', level=1)
        logger.info(
            f'User specified assignments: {", ".join([x.name for x in assignments])}')
        _, remain, _ = self._limit_status
        for assignment in assignments:
            if assignment in self.dispatched:
                continue
            logger.hr('Assignment inlist', level=2)
            logger.info(f'Check assignment inlist: {assignment}')
            self.goto_entry(assignment)
            status = self._check_assignment_status()
            if status == AssignmentStatus.CLAIMABLE:
                self.claim(assignment, duration, should_redispatch=True)
                continue
            if status == AssignmentStatus.DISPATCHED:
                self.dispatched[assignment] = datetime.now() + \
                    self._get_assignment_time()
                continue
            # General assignments must be dispatchable here
            if remain <= 0:
                yield assignment
                continue
            self.dispatch(assignment, duration)
            remain -= 1

    def _check_all(self):
        """
        States of assignments from top to bottom are in following order:
            1. Claimable
            2. Dispatched
            3. Dispatchable
        Break when a dispatchable assignment is encountered
        """
        logger.hr('Assignment check all', level=1)
        current, remain, _ = self._limit_status
        # current = #Claimable + #Dispatched
        if current == len(self.dispatched):
            return remain
        for group in self._iter_groups():
            self.goto_group(group)
            insight = False
            for assignment in self._iter_entries():
                if assignment in self.dispatched:
                    continue
                logger.hr('Assignment all', level=2)
                logger.info(f'Check assignment all: {assignment}')
                self.goto_entry(assignment, insight)
                status = self._check_assignment_status()
                if status == AssignmentStatus.CLAIMABLE:
                    self.claim(assignment, None, should_redispatch=False)
                    current -= 1
                    remain += 1
                    insight = True  # Order of entries change after claiming
                    if current == len(self.dispatched):
                        return remain
                    continue
                if status == AssignmentStatus.DISPATCHED:
                    self.dispatched[assignment] = datetime.now() + \
                        self._get_assignment_time()
                    insight = False  # Order of entries does not change here
                    if current == len(self.dispatched):
                        return remain
                    continue
                break
        return remain

    def _dispatch_remain(self, duration: int, remain: int):
        """
        Dispatch assignments according to preset priority

        Args:
            duration (int): user specified duration
            remain (int): 
                The number of remaining assignments after
                processing the ones specified by user
        """
        if remain <= 0:
            return
        logger.hr('Assignment dispatch remain', level=2)
        logger.warning(f'{remain} remain')
        logger.info(
            'Dispatch remaining assignments according to preset priority')
        group_priority = (
            KEYWORDS_ASSIGNMENT_GROUP.EXP_Materials_Credits,
            KEYWORDS_ASSIGNMENT_GROUP.Character_Materials,
            KEYWORDS_ASSIGNMENT_GROUP.Synthesis_Materials
        )
        for group in group_priority:
            for assignment in group.entries:
                if assignment in self.dispatched:
                    continue
                self.goto_entry(assignment)
                self.dispatch(assignment, duration)
                remain -= 1
                if remain <= 0:
                    return

    def _dispatch_event(self, remain: int):
        if remain <= 0:
            return remain
        logger.hr('Assignment dispatch event', level=1)
        for group in self._iter_groups():
            if not isinstance(group, AssignmentEventGroup):
                continue
            self.goto_group(group)
            for assignment in self._iter_entries():
                if assignment in self.dispatched:
                    continue
                logger.hr('Assignment event', level=2)
                logger.info(f'Check assignment event: {assignment}')
                # Order of entries does not change during iteration
                self.goto_entry(assignment, insight=False)
                status = self._check_assignment_status()
                # Should only be dispatchable or locked after _check_all
                if status == AssignmentStatus.DISPATCHABLE:
                    self.dispatch(assignment, None)
                    remain -= 1
                    if remain <= 0:
                        return remain
                    continue
                break
        return remain
