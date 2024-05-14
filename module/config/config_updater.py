import re
import typing as t
from copy import deepcopy

from cached_property import cached_property

from deploy.Windows.utils import DEPLOY_TEMPLATE, poor_yaml_read, poor_yaml_write
from module.base.timer import timer
from module.config.convert import *
from module.config.server import VALID_SERVER
from module.config.utils import *

CONFIG_IMPORT = '''
import datetime

# This file was automatically generated by module/config/config_updater.py.
# Don't modify it manually.


class GeneratedConfig:
    """
    Auto generated configuration
    """
'''.strip().split('\n')

DICT_GUI_TO_INGAME = {
    'zh-CN': 'cn',
    'en-US': 'en',
    'ja-JP': 'jp',
    'zh-TW': 'cht',
    'es-ES': 'es',
}


def gui_lang_to_ingame_lang(lang: str) -> str:
    return DICT_GUI_TO_INGAME.get(lang, 'en')


def get_generator():
    from module.base.code_generator import CodeGenerator
    return CodeGenerator()


class ConfigGenerator:
    @cached_property
    def argument(self):
        """
        Load argument.yaml, and standardise its structure.

        <group>:
            <argument>:
                type: checkbox|select|textarea|input
                value:
                option (Optional): Options, if argument has any options.
                validate (Optional): datetime
        """
        data = {}
        raw = read_file(filepath_argument('argument'))

        def option_add(keys, options):
            options = deep_get(raw, keys=keys, default=[]) + options
            deep_set(raw, keys=keys, value=options)

        # Insert packages
        option_add(keys='Emulator.PackageName.option', options=list(VALID_SERVER.keys()))
        # Insert dungeons
        from tasks.dungeon.keywords import DungeonList
        calyx_golden = [dungeon.name for dungeon in DungeonList.instances.values() if dungeon.is_Calyx_Golden_Memories] \
            + [dungeon.name for dungeon in DungeonList.instances.values() if dungeon.is_Calyx_Golden_Aether] \
            + [dungeon.name for dungeon in DungeonList.instances.values() if dungeon.is_Calyx_Golden_Treasures]
        # calyx_crimson
        from tasks.rogue.keywords import KEYWORDS_ROGUE_PATH as Path
        order = [Path.Destruction, Path.Preservation, Path.The_Hunt, Path.Abundance,
                 Path.Erudition, Path.The_Harmony, Path.Nihility]
        calyx_crimson = []
        for path in order:
            calyx_crimson += [dungeon.name for dungeon in DungeonList.instances.values()
                              if dungeon.Calyx_Crimson_Path == path]
        # stagnant_shadow
        from tasks.character.keywords import CombatType
        stagnant_shadow = []
        for type_ in CombatType.instances.values():
            stagnant_shadow += [dungeon.name for dungeon in DungeonList.instances.values()
                                if dungeon.Stagnant_Shadow_Combat_Type == type_]
        cavern_of_corrosion = [dungeon.name for dungeon in DungeonList.instances.values() if dungeon.is_Cavern_of_Corrosion]
        option_add(
            keys='Dungeon.Name.option',
            options=calyx_golden + calyx_crimson + stagnant_shadow + cavern_of_corrosion
        )
        # Double events
        option_add(keys='Dungeon.NameAtDoubleCalyx.option', options=calyx_golden + calyx_crimson)
        option_add(keys='Dungeon.NameAtDoubleRelic.option', options=cavern_of_corrosion)
        # Dungeon daily
        option_add(keys='DungeonDaily.CalyxGolden.option', options=calyx_golden)
        option_add(keys='DungeonDaily.CalyxCrimson.option', options=calyx_crimson)
        option_add(keys='DungeonDaily.StagnantShadow.option', options=stagnant_shadow)
        option_add(keys='DungeonDaily.CavernOfCorrosion.option', options=cavern_of_corrosion)
        option_add(
            keys='Weekly.Name.option',
            options=[dungeon.name for dungeon in DungeonList.instances.values() if dungeon.is_Echo_of_War])
        # Insert characters
        from tasks.character.keywords import CharacterList
        unsupported_characters = ["Boothill", "TrailblazerHarmony"]
        characters = [character.name for character in CharacterList.instances.values()
                      if character.name not in unsupported_characters]
        option_add(keys='DungeonSupport.Character.option', options=characters)
        # Insert daily quests
        from tasks.daily.keywords import DailyQuest
        for quest in DailyQuest.instances.values():
            quest: DailyQuest
            deep_set(raw, keys=['AchievableQuest', quest.name], value={
                'type': 'state',
                'value': 'achievable',
                'option': ['achievable', 'not_set', 'not_supported'],
                'option_bold': ['achievable'],
                'option_light': ['not_supported'],
            })
        # Insert assignments
        from tasks.assignment.keywords import AssignmentEntry
        assignments = [entry.name for entry in AssignmentEntry.instances.values()]
        for i in range(4):
            option_add(keys=f'Assignment.Name_{i + 1}.option', options=assignments)

        # Load
        for path, value in deep_iter(raw, depth=2):
            arg = {
                'type': 'input',
                'value': '',
                # option
            }
            if not isinstance(value, dict):
                value = {'value': value}
            arg['type'] = data_to_type(value, arg=path[1])
            if arg['type'] == 'stored':
                value['value'] = {}
                arg['display'] = 'hide'  # Hide `stored` by default
            if isinstance(value['value'], datetime):
                arg['type'] = 'datetime'
                arg['validate'] = 'datetime'
            # Manual definition has the highest priority
            arg.update(value)
            deep_set(data, keys=path, value=arg)

        return data

    @cached_property
    def task(self):
        """
        <task_group>:
            <task>:
                <group>:
        """
        return read_file(filepath_argument('task'))

    @cached_property
    def default(self):
        """
        <task>:
            <group>:
                <argument>: value
        """
        return read_file(filepath_argument('default'))

    @cached_property
    def override(self):
        """
        <task>:
            <group>:
                <argument>: value
        """
        return read_file(filepath_argument('override'))

    @cached_property
    def gui(self):
        """
        <i18n_group>:
            <i18n_key>: value, value is None
        """
        return read_file(filepath_argument('gui'))

    @cached_property
    @timer
    def args(self):
        """
        Merge definitions into standardised json.

            task.yaml ---+
        argument.yaml ---+-----> args.json
        override.yaml ---+
         default.yaml ---+

        """
        # Construct args
        data = {}
        for path, groups in deep_iter(self.task, depth=3):
            if 'tasks' not in path:
                continue
            task = path[2]
            # Add storage to all task
            # groups.append('Storage')
            for group in groups:
                if group not in self.argument:
                    print(f'`{task}.{group}` is not related to any argument group')
                    continue
                deep_set(data, keys=[task, group], value=deepcopy(self.argument[group]))

        def check_override(path, value):
            # Check existence
            old = deep_get(data, keys=path, default=None)
            if old is None:
                print(f'`{".".join(path)}` is not a existing argument')
                return False
            # Check type
            # But allow `Interval` to be different
            old_value = old.get('value', None) if isinstance(old, dict) else old
            value = old.get('value', None) if isinstance(value, dict) else value
            if type(value) != type(old_value) \
                    and old_value is not None \
                    and path[2] not in ['SuccessInterval', 'FailureInterval']:
                print(
                    f'`{value}` ({type(value)}) and `{".".join(path)}` ({type(old_value)}) are in different types')
                return False
            # Check option
            if isinstance(old, dict) and 'option' in old:
                if value not in old['option']:
                    print(f'`{value}` is not an option of argument `{".".join(path)}`')
                    return False
            return True

        # Set defaults
        for p, v in deep_iter(self.default, depth=3):
            if not check_override(p, v):
                continue
            deep_set(data, keys=p + ['value'], value=v)
        # Override non-modifiable arguments
        for p, v in deep_iter(self.override, depth=3):
            if not check_override(p, v):
                continue
            if isinstance(v, dict):
                typ = v.get('type')
                if typ == 'state':
                    pass
                elif typ == 'lock':
                    deep_default(v, keys='display', value="disabled")
                elif deep_get(v, keys='value') is not None:
                    deep_default(v, keys='display', value='hide')
                for arg_k, arg_v in v.items():
                    deep_set(data, keys=p + [arg_k], value=arg_v)
            else:
                deep_set(data, keys=p + ['value'], value=v)
                deep_set(data, keys=p + ['display'], value='hide')
        # Set command
        for path, groups in deep_iter(self.task, depth=3):
            if 'tasks' not in path:
                continue
            task = path[2]
            if deep_get(data, keys=f'{task}.Scheduler.Command'):
                deep_set(data, keys=f'{task}.Scheduler.Command.value', value=task)
                deep_set(data, keys=f'{task}.Scheduler.Command.display', value='hide')

        return data

    @timer
    def generate_code(self):
        """
        Generate python code.

        args.json ---> config_generated.py

        """
        visited_group = set()
        visited_path = set()
        lines = CONFIG_IMPORT
        for path, data in deep_iter(self.argument, depth=2):
            group, arg = path
            if group not in visited_group:
                lines.append('')
                lines.append(f'    # Group `{group}`')
                visited_group.add(group)

            option = ''
            if 'option' in data and data['option']:
                option = '  # ' + ', '.join([str(opt) for opt in data['option']])
            path = '.'.join(path)
            lines.append(f'    {path_to_arg(path)} = {repr(parse_value(data["value"], data=data))}{option}')
            visited_path.add(path)

        with open(filepath_code(), 'w', encoding='utf-8', newline='') as f:
            for text in lines:
                f.write(text + '\n')

    @timer
    def generate_stored(self):
        import module.config.stored.classes as classes
        gen = get_generator()
        gen.add('from module.config.stored.classes import (')
        with gen.tab():
            for cls in sorted([name for name in dir(classes) if name.startswith('Stored')]):
                gen.add(cls + ',')
        gen.add(')')
        gen.Empty()
        gen.Empty()
        gen.Empty()
        gen.CommentAutoGenerage('module/config/config_updater.py')

        with gen.Class('StoredGenerated'):
            for path, data in deep_iter(self.args, depth=3):
                cls = data.get('stored')
                if cls:
                    gen.add(f'{path[-1]} = {cls}("{".".join(path)}")')

        gen.write('module/config/stored/stored_generated.py')

    @timer
    def generate_i18n(self, lang):
        """
        Load old translations and generate new translation file.

                     args.json ---+-----> i18n/<lang>.json
        (old) i18n/<lang>.json ---+

        """
        new = {}
        old = read_file(filepath_i18n(lang))

        def deep_load(keys, default=True, words=('name', 'help')):
            for word in words:
                k = keys + [str(word)]
                d = ".".join(k) if default else str(word)
                v = deep_get(old, keys=k, default=d)
                deep_set(new, keys=k, value=v)

        # Menu
        for path, data in deep_iter(self.task, depth=3):
            if 'tasks' not in path:
                continue
            task_group, _, task = path
            deep_load(['Menu', task_group])
            deep_load(['Task', task])
        # Arguments
        visited_group = set()
        for path, data in deep_iter(self.argument, depth=2):
            if path[0] not in visited_group:
                deep_load([path[0], '_info'])
                visited_group.add(path[0])
            deep_load(path)
            if 'option' in data:
                deep_load(path, words=data['option'], default=False)

        # Package names
        # for package, server in VALID_PACKAGE.items():
        #     path = ['Emulator', 'PackageName', package]
        #     if deep_get(new, keys=path) == package:
        #         deep_set(new, keys=path, value=server.upper())
        # for package, server_and_channel in VALID_CHANNEL_PACKAGE.items():
        #     server, channel = server_and_channel
        #     name = deep_get(new, keys=['Emulator', 'PackageName', to_package(server)])
        #     if lang == SERVER_TO_LANG[server]:
        #         value = f'{name} {channel}渠道服 {package}'
        #     else:
        #         value = f'{name} {package}'
        #     deep_set(new, keys=['Emulator', 'PackageName', package], value=value)
        # Game server names
        # for server, _list in VALID_SERVER_LIST.items():
        #     for index in range(len(_list)):
        #         path = ['Emulator', 'ServerName', f'{server}-{index}']
        #         prefix = server.split('_')[0].upper()
        #         prefix = '国服' if prefix == 'CN' else prefix
        #         deep_set(new, keys=path, value=f'[{prefix}] {_list[index]}')

        ingame_lang = gui_lang_to_ingame_lang(lang)
        dailies = deep_get(self.argument, keys='Dungeon.Name.option')
        # Dungeon names
        i18n_memories = {
            'cn': '材料：角色经验（{dungeon}）',
            'cht': '材料：角色經驗（{dungeon}）',
            'jp': '素材：役割経験（{dungeon}）：',
            'en': 'Material: Character EXP ({dungeon})',
            'es': 'Material: EXP de personaje ({dungeon})',
        }
        i18n_aether = {
            'cn': '材料：武器经验（{dungeon}）',
            'cht': '材料：武器經驗（{dungeon}）',
            'jp': '素材：武器経験（{dungeon}）：',
            'en': 'Material: Light Cone EXP ({dungeon})',
            'es': 'Material: EXP de conos de luz ({dungeon})',
        }
        i18n_treasure = {
            'cn': '材料：信用点（{dungeon}）',
            'cht': '材料：信用點（{dungeon}）',
            'jp': '素材：クレジット（{dungeon}）',
            'en': 'Material: Credit ({dungeon})',
            'es': 'Material: Créditos ({dungeon})',
        }
        i18n_crimson = {
            'cn': '行迹材料：{path}（{plane}）',
            'cht': '行跡材料：{path}（{plane}）',
            'jp': '軌跡素材：{path}（{plane}）',
            'en': 'Trace: {path} ({plane})',
            'es': 'Rastros: {path} ({plane})',
        }
        i18n_relic = {
            'cn': '（{dungeon}）',
            'cht': '（{dungeon}）',
            'jp': '（{dungeon}）',
            'en': ' ({dungeon})',
            'es': ' ({dungeon})',
        }
        from tasks.dungeon.keywords import DungeonList, DungeonDetailed
        for dungeon in DungeonList.instances.values():
            dungeon: DungeonList = dungeon
            if not dungeon.plane:
                continue
            dungeon_name = dungeon.__getattribute__(ingame_lang)
            dungeon_name = re.sub('[「」]', '', dungeon_name)
            plane = dungeon.plane.__getattribute__(ingame_lang)
            plane = re.sub('[「」]', '', plane)
            if dungeon.is_Calyx_Golden_Memories:
                deep_set(new, keys=['Dungeon', 'Name', dungeon.name],
                         value=i18n_memories[ingame_lang].format(dungeon=dungeon_name))
            if dungeon.is_Calyx_Golden_Aether:
                deep_set(new, keys=['Dungeon', 'Name', dungeon.name],
                         value=i18n_aether[ingame_lang].format(dungeon=dungeon_name))
            if dungeon.is_Calyx_Golden_Treasures:
                deep_set(new, keys=['Dungeon', 'Name', dungeon.name],
                         value=i18n_treasure[ingame_lang].format(dungeon=dungeon_name))
            if dungeon.is_Calyx_Crimson:
                path = dungeon.Calyx_Crimson_Path.__getattribute__(ingame_lang)
                deep_set(new, keys=['Dungeon', 'Name', dungeon.name],
                         value=i18n_crimson[ingame_lang].format(path=path, plane=plane))
            if dungeon.is_Cavern_of_Corrosion:
                value = deep_get(new, keys=['Dungeon', 'Name', dungeon.name], default='')
                suffix = i18n_relic[ingame_lang].format(dungeon=dungeon_name).replace('Cavern of Corrosion: ', '')
                if not value.endswith(suffix):
                    deep_set(new, keys=['Dungeon', 'Name', dungeon.name], value=f'{value}{suffix}')

        # Stagnant shadows with character names
        for dungeon in DungeonDetailed.instances.values():
            if dungeon.name in dailies:
                value = dungeon.__getattribute__(ingame_lang)
                deep_set(new, keys=['Dungeon', 'Name', dungeon.name], value=value)

        # Copy dungeon i18n to double events
        def update_dungeon_names(keys):
            for dungeon in deep_get(self.argument, keys=f'{keys}.option', default=[]):
                value = deep_get(new, keys=['Dungeon', 'Name', dungeon])
                if value:
                    deep_set(new, keys=f'{keys}.{dungeon}', value=value)

        update_dungeon_names('Dungeon.NameAtDoubleCalyx')
        update_dungeon_names('Dungeon.NameAtDoubleRelic')
        update_dungeon_names('DungeonDaily.CalyxGolden')
        update_dungeon_names('DungeonDaily.CalyxCrimson')
        update_dungeon_names('DungeonDaily.StagnantShadow')
        update_dungeon_names('DungeonDaily.CavernOfCorrosion')

        # Character names
        from tasks.character.keywords import CharacterList
        characters = deep_get(self.argument, keys='DungeonSupport.Character.option')
        for character in CharacterList.instances.values():
            if character.name in characters:
                value = character.__getattribute__(ingame_lang)
                if "Trailblazer" in value:
                    continue
                deep_set(new, keys=['DungeonSupport', 'Character', character.name], value=value)

        # Daily quests
        from tasks.daily.keywords import DailyQuest
        for quest in DailyQuest.instances.values():
            value = quest.__getattribute__(ingame_lang)
            deep_set(new, keys=['AchievableQuest', quest.name, 'name'], value=value)
            # deep_set(new, keys=['DailyQuest', quest.name, 'help'], value='')
            copy_from = 'Complete_1_Daily_Mission'
            if quest.name != copy_from:
                for option in deep_get(self.args, keys=['DailyQuest', 'AchievableQuest', copy_from, 'option']):
                    value = deep_get(new, keys=['AchievableQuest', copy_from, option])
                    deep_set(new, keys=['AchievableQuest', quest.name, option], value=value)

        # Assignments
        from tasks.assignment.keywords import AssignmentEntryDetailed
        for entry in AssignmentEntryDetailed.instances.values():
            entry: AssignmentEntryDetailed
            value = entry.__getattribute__(ingame_lang)
            for i in range(4):
                deep_set(new, keys=['Assignment', f'Name_{i + 1}', entry.name], value=value)

        # Echo of War
        dungeons = [d for d in DungeonList.instances.values() if d.is_Echo_of_War]
        for dungeon in dungeons:
            world = dungeon.plane.world
            world_name = world.__getattribute__(ingame_lang)
            dungeon_name = dungeon.__getattribute__(ingame_lang).replace('Echo of War: ', '')
            value = f'{dungeon_name} ({world_name})'
            deep_set(new, keys=['Weekly', 'Name', dungeon.name], value=value)
        # Rogue worlds
        for dungeon in [d for d in DungeonList.instances.values() if d.is_Simulated_Universe]:
            name = deep_get(new, keys=['RogueWorld', 'World', dungeon.name], default=None)
            if name:
                deep_set(new, keys=['RogueWorld', 'World', dungeon.name], value=dungeon.__getattribute__(ingame_lang))

        # GUI i18n
        for path, _ in deep_iter(self.gui, depth=2):
            group, key = path
            deep_load(keys=['Gui', group], words=(key,))

        # zh-TW
        dic_repl = {
            '設置': '設定',
            '支持': '支援',
            '啓': '啟',
            '异': '異',
            '服務器': '伺服器',
            '文件': '檔案',
            '自定義': '自訂'
        }
        if lang == 'zh-TW':
            for path, value in deep_iter(new, depth=3):
                for before, after in dic_repl.items():
                    value = value.replace(before, after)
                deep_set(new, keys=path, value=value)

        write_file(filepath_i18n(lang), new)

    @cached_property
    def menu(self):
        """
        Generate menu definitions

        task.yaml --> menu.json

        """
        data = {}
        for task_group in self.task.keys():
            value = deep_get(self.task, keys=[task_group, 'menu'])
            if value not in ['collapse', 'list']:
                value = 'collapse'
            deep_set(data, keys=[task_group, 'menu'], value=value)
            value = deep_get(self.task, keys=[task_group, 'page'])
            if value not in ['setting', 'tool']:
                value = 'setting'
            deep_set(data, keys=[task_group, 'page'], value=value)
            tasks = deep_get(self.task, keys=[task_group, 'tasks'], default={})
            tasks = list(tasks.keys())
            deep_set(data, keys=[task_group, 'tasks'], value=tasks)

        # Simulated universe is WIP, task won't show on GUI but can still be bound
        # e.g. `RogueUI('src', task='Rogue')`
        # Comment this for development
        # data.pop('Rogue')

        return data

    @cached_property
    def stored(self):
        import module.config.stored.classes as classes
        data = {}
        for path, value in deep_iter(self.args, depth=3):
            if value.get('type') != 'stored':
                continue
            name = path[-1]
            stored = value.get('stored')
            stored_class = getattr(classes, stored)
            row = {
                'name': name,
                'path': '.'.join(path),
                'i18n': f'{path[1]}.{path[2]}.name',
                'stored': stored,
                'attrs': stored_class('')._attrs,
                'order': value.get('order', 0),
                'color': value.get('color', '#777777')
            }
            data[name] = row

        # sort by `order` ascending, but `order`==0 at last
        data = sorted(data.items(), key=lambda kv: (kv[1]['order'] == 0, kv[1]['order']))
        data = {k: v for k, v in data}
        return data

    @staticmethod
    def generate_deploy_template():
        template = poor_yaml_read(DEPLOY_TEMPLATE)
        cn = {
            'Repository': 'cn',
            'PypiMirror': 'https://pypi.tuna.tsinghua.edu.cn/simple',
            'Language': 'zh-CN',
        }
        aidlux = {
            'GitExecutable': '/usr/bin/git',
            'PythonExecutable': '/usr/bin/python',
            'RequirementsFile': './deploy/AidLux/0.92/requirements.txt',
            'AdbExecutable': '/usr/bin/adb',
        }

        docker = {
            'GitExecutable': '/usr/bin/git',
            'PythonExecutable': '/usr/local/bin/python',
            'RequirementsFile': './deploy/docker/requirements.txt',
            'AdbExecutable': '/usr/bin/adb',
        }

        def update(suffix, *args):
            file = f'./config/deploy.{suffix}.yaml'
            new = deepcopy(template)
            for dic in args:
                new.update(dic)
            poor_yaml_write(data=new, file=file)

        update('template')
        update('template-cn', cn)
        # update('template-AidLux', aidlux)
        # update('template-AidLux-cn', aidlux, cn)
        # update('template-docker', docker)
        # update('template-docker-cn', docker, cn)

        tpl = {
            'Repository': '{{repository}}',
            'GitExecutable': '{{gitExecutable}}',
            'PythonExecutable': '{{pythonExecutable}}',
            'AdbExecutable': '{{adbExecutable}}',
            'Language': '{{language}}',
            'Theme': '{{theme}}',
        }

        def update(file, *args):
            new = deepcopy(template)
            for dic in args:
                new.update(dic)
            poor_yaml_write(data=new, file=file)

        update('./webapp/packages/main/public/deploy.yaml.tpl', tpl)

    @timer
    def generate(self):
        _ = self.args
        _ = self.menu
        _ = self.stored
        # _ = self.event
        # self.insert_server()
        write_file(filepath_args(), self.args)
        write_file(filepath_args('menu'), self.menu)
        write_file(filepath_args('stored'), self.stored)
        self.generate_code()
        self.generate_stored()
        for lang in LANGUAGES:
            self.generate_i18n(lang)
        self.generate_deploy_template()


class ConfigUpdater:
    # source, target, (optional)convert_func
    redirection = [
        ('Dungeon.Dungeon.Name', 'Dungeon.Dungeon.Name', convert_20_dungeon),
        ('Dungeon.Dungeon.NameAtDoubleCalyx', 'Dungeon.Dungeon.NameAtDoubleCalyx', convert_20_dungeon),
        ('Dungeon.DungeonDaily.CalyxGolden', 'Dungeon.DungeonDaily.CalyxGolden', convert_20_dungeon),
        ('Dungeon.DungeonDaily.CalyxCrimson', 'Dungeon.DungeonDaily.CalyxCrimson', convert_20_dungeon),
        ('Rogue.RogueWorld.SimulatedUniverseElite', 'Rogue.RogueWorld.SimulatedUniverseFarm', convert_rogue_farm),
    ]

    @cached_property
    def args(self):
        return read_file(filepath_args())

    def config_update(self, old, is_template=False):
        """
        Args:
            old (dict):
            is_template (bool):

        Returns:
            dict:
        """
        new = {}

        def deep_load(keys):
            data = deep_get(self.args, keys=keys, default={})
            value = deep_get(old, keys=keys, default=data['value'])
            typ = data['type']
            display = data.get('display')
            if is_template or value is None or value == '' \
                    or typ in ['lock', 'state'] or (display == 'hide' and typ != 'stored'):
                value = data['value']
            value = parse_value(value, data=data)
            deep_set(new, keys=keys, value=value)

        for path, _ in deep_iter(self.args, depth=3):
            deep_load(path)

        if not is_template:
            new = self.config_redirect(old, new)
        new = self.update_state(new)

        return new

    def config_redirect(self, old, new):
        """
        Convert old settings to the new.

        Args:
            old (dict):
            new (dict):

        Returns:
            dict:
        """
        for row in self.redirection:
            if len(row) == 2:
                source, target = row
                update_func = None
            elif len(row) == 3:
                source, target, update_func = row
            else:
                continue

            if isinstance(source, tuple):
                value = []
                error = False
                for attribute in source:
                    tmp = deep_get(old, keys=attribute)
                    if tmp is None:
                        error = True
                        continue
                    value.append(tmp)
                if error:
                    continue
            else:
                value = deep_get(old, keys=source)
                if value is None:
                    continue

            if update_func is not None:
                value = update_func(value)

            if isinstance(target, tuple):
                for k, v in zip(target, value):
                    # Allow update same key
                    if (deep_get(old, keys=k) is None) or (source == target):
                        deep_set(new, keys=k, value=v)
            elif (deep_get(old, keys=target) is None) or (source == target):
                deep_set(new, keys=target, value=value)

        return new

    @staticmethod
    def update_state(data):
        def set_daily(quest, value):
            if value is True:
                value = 'achievable'
            if value is False:
                value = 'not_set'
            deep_set(data, keys=['DailyQuest', 'AchievableQuest', quest], value=value)

        set_daily('Complete_1_Daily_Mission', 'not_supported')
        # Dungeon
        dungeon = deep_get(data, keys='Dungeon.Scheduler.Enable')
        set_daily('Clear_Calyx_Golden_1_times',
                  dungeon and deep_get(data, 'Dungeon.DungeonDaily.CalyxGolden') != 'do_not_achieve')
        set_daily('Clear_Calyx_Crimson_1_times',
                  dungeon and deep_get(data, 'Dungeon.DungeonDaily.CalyxCrimson') != 'do_not_achieve')
        set_daily('Clear_Stagnant_Shadow_1_times',
                  dungeon and deep_get(data, 'Dungeon.DungeonDaily.StagnantShadow') != 'do_not_achieve')
        set_daily('Clear_Cavern_of_Corrosion_1_times',
                  dungeon and deep_get(data, 'Dungeon.DungeonDaily.CavernOfCorrosion') != 'do_not_achieve')
        # Combat requirements
        set_daily('In_a_single_battle_inflict_3_Weakness_Break_of_different_Types', 'achievable')
        set_daily('Inflict_Weakness_Break_5_times', 'achievable')
        set_daily('Defeat_a_total_of_20_enemies', 'achievable')
        set_daily('Enter_combat_by_attacking_enemie_Weakness_and_win_3_times', 'achievable')
        set_daily('Use_Technique_2_times', 'achievable')
        # Other game systems
        set_daily('Dispatch_1_assignments', deep_get(data, 'Assignment.Scheduler.Enable'))
        set_daily('Take_photos_1_times', 'achievable')
        set_daily('Destroy_3_destructible_objects', 'achievable')
        set_daily('Complete_Forgotten_Hall_1_time', 'achievable')
        set_daily('Complete_Echo_of_War_1_times', deep_get(data, 'Weekly.Scheduler.Enable'))
        set_daily('Complete_Simulated_Universe_1_times',
                  deep_get(data, 'Rogue.Scheduler.Enable'))
        set_daily('Obtain_victory_in_combat_with_Support_Characters_1_times',
                  dungeon and deep_get(data, 'Dungeon.DungeonSupport.Use') in ['when_daily', 'always_use'])
        set_daily('Use_an_Ultimate_to_deal_the_final_blow_1_time', 'achievable')
        # Build
        set_daily('Level_up_any_character_1_times', 'not_supported')
        set_daily('Level_up_any_Light_Cone_1_times', 'not_supported')
        set_daily('Level_up_any_Relic_1_times', 'not_supported')
        # Items
        set_daily('Salvage_any_Relic', 'achievable')
        set_daily('Use_the_Omni_Synthesizer_1_times', 'achievable')
        set_daily('Use_Consumables_1_time', 'achievable')

        # Limit setting combinations
        if deep_get(data, keys='Rogue.RogueWorld.UseImmersifier') is False:
            deep_set(data, keys='Rogue.RogueWorld.UseStamina', value=False)
        if deep_get(data, keys='Rogue.RogueWorld.UseStamina') is True:
            deep_set(data, keys='Rogue.RogueWorld.UseImmersifier', value=True)
        if deep_get(data, keys='Rogue.RogueWorld.DoubleEvent') is True:
            deep_set(data, keys='Rogue.RogueWorld.UseImmersifier', value=True)
        # Store immersifier in dungeon task
        if deep_get(data, keys='Rogue.RogueWorld.UseImmersifier') is True:
            deep_set(data, keys='Dungeon.Scheduler.Enable', value=True)
        # Cloud settings
        if deep_get(data, keys='Alas.Emulator.GameClient') == 'cloud_android':
            deep_set(data, keys='Alas.Emulator.PackageName', value='CN-Official')

        return data

    def save_callback(self, key: str, value: t.Any) -> t.Iterable[t.Tuple[str, t.Any]]:
        """
        Args:
            key: Key path in config json, such as "Main.Emotion.Fleet1Value"
            value: Value set by user, such as "98"

        Yields:
            str: Key path to set config json, such as "Main.Emotion.Fleet1Record"
            any: Value to set, such as "2020-01-01 00:00:00"
        """
        if key.startswith('Dungeon.Dungeon') or key.startswith('Dungeon.DungeonDaily'):
            from tasks.dungeon.keywords.dungeon import DungeonList
            from module.exception import ScriptError
            try:
                dungeon = DungeonList.find(value)
            except ScriptError:
                return
            if key.endswith('Name'):
                if dungeon.is_Calyx_Golden:
                    yield 'Dungeon.Dungeon.NameAtDoubleCalyx', value
                    yield 'Dungeon.DungeonDaily.CalyxGolden', value
                elif dungeon.is_Calyx_Crimson:
                    yield 'Dungeon.Dungeon.NameAtDoubleCalyx', value
                    yield 'Dungeon.DungeonDaily.CalyxCrimson', value
                elif dungeon.is_Stagnant_Shadow:
                    yield 'Dungeon.DungeonDaily.StagnantShadow', value
                elif dungeon.is_Cavern_of_Corrosion:
                    yield 'Dungeon.Dungeon.NameAtDoubleRelic', value
                    yield 'Dungeon.DungeonDaily.CavernOfCorrosion', value
            elif key.endswith('NameAtDoubleCalyx'):
                if dungeon.is_Calyx_Golden:
                    yield 'Dungeon.DungeonDaily.CalyxGolden', value
                elif dungeon.is_Calyx_Crimson:
                    yield 'Dungeon.DungeonDaily.CalyxCrimson', value
            elif key.endswith('NameAtDoubleRelic'):
                yield 'Dungeon.DungeonDaily.CavernOfCorrosion', value
            elif key.endswith('CavernOfCorrosion'):
                yield 'Dungeon.Dungeon.NameAtDoubleRelic', value
        elif key == 'Rogue.RogueWorld.UseImmersifier' and value is False:
            yield 'Rogue.RogueWorld.UseStamina', False
        elif key == 'Rogue.RogueWorld.UseStamina' and value is True:
            yield 'Rogue.RogueWorld.UseImmersifier', True
        elif key == 'Rogue.RogueWorld.DoubleEvent' and value is True:
            yield 'Rogue.RogueWorld.UseImmersifier', True
        elif key == 'Alas.Emulator.GameClient' and value == 'cloud_android':
            yield 'Alas.Emulator.PackageName', 'CN-Official'
            yield 'Alas.Optimization.WhenTaskQueueEmpty', 'close_game'

    def iter_hidden_args(self, data) -> t.Iterator[str]:
        """
        Args:
            data (dict): config

        Yields:
            str: Arg path that should be hidden
        """
        if deep_get(data, 'Rogue.RogueBlessing.PresetBlessingFilter') != 'custom':
            yield 'Rogue.RogueBlessing.CustomBlessingFilter'
        if deep_get(data, 'Rogue.RogueBlessing.PresetResonanceFilter') != 'custom':
            yield 'Rogue.RogueBlessing.CustomResonanceFilter'
        if deep_get(data, 'Rogue.RogueBlessing.PresetCurioFilter') != 'custom':
            yield 'Rogue.RogueBlessing.CustomCurioFilter'
        if deep_get(data, 'Dungeon.DungeonMode.Mode') != 'timer':
            yield 'Dungeon.DungeonMode.Delay'
        if deep_get(data, 'Rogue.RogueWorld.WeeklyFarming', default=False) is False:
            yield 'Rogue.RogueWorld.SimulatedUniverseFarm'

    def get_hidden_args(self, data) -> t.Set[str]:
        """
        Return a set of hidden args
        """
        out = list(self.iter_hidden_args(data))
        return set(out)

    def read_file(self, config_name, is_template=False):
        """
        Read and update config file.

        Args:
            config_name (str): ./config/{file}.json
            is_template (bool):

        Returns:
            dict:
        """
        old = read_file(filepath_config(config_name))
        new = self.config_update(old, is_template=is_template)
        # The updated config did not write into file, although it doesn't matters.
        # Commented for performance issue
        # self.write_file(config_name, new)
        return new

    @staticmethod
    def write_file(config_name, data, mod_name='alas'):
        """
        Write config file.

        Args:
            config_name (str): ./config/{file}.json
            data (dict):
            mod_name (str):
        """
        write_file(filepath_config(config_name, mod_name), data)

    @timer
    def update_file(self, config_name, is_template=False):
        """
        Read, update and write config file.

        Args:
            config_name (str): ./config/{file}.json
            is_template (bool):

        Returns:
            dict:
        """
        data = self.read_file(config_name, is_template=is_template)
        self.write_file(config_name, data)
        return data


if __name__ == '__main__':
    """
    Process the whole config generation.

                 task.yaml -+----------------> menu.json
             argument.yaml -+-> args.json ---> config_generated.py
             override.yaml -+       |
                  gui.yaml --------\|
                                   ||
    (old) i18n/<lang>.json --------\\========> i18n/<lang>.json
    (old)    template.json ---------\========> template.json
    """
    # Ensure running in Alas root folder
    import os

    os.chdir(os.path.join(os.path.dirname(__file__), '../../'))

    ConfigGenerator().generate()
    ConfigUpdater().update_file('template', is_template=True)
