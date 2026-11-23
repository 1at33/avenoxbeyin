"""Hybrid H2: where the whole protected core fits, topic detail beyond its floor fills at half rate
while an identity file is still clipped; the protected core and tight openings stay as they were."""
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get('BEYIN_TEST_REPO', Path(__file__).resolve().parents[1]))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evaluator = load('beyin_v3_lift_evaluator', 'scripts/evaluate_v3.py')
companion = load('beyin_v3_lift_companion', 'template/.claude/scripts/beyin_v3_companion.py')
COMPANION = '🔮 850-Companion'


def filler(title, size, tag):
    out, i = f'# {title}\n', 0
    while len(out) < size:
        out += f'- {tag}{i:03d}: bu satır sentetik içeriktir ve kısa cümlelerle yazılmıştır.\n'
        i += 1
    return out + f'- {tag}_END\n'


def section(text, name):
    match = re.search(r'\n\[' + re.escape(COMPANION) + '/' + re.escape(name) + r'\]\n(.*?)(?=\n\[[^\]\n]+\]\n|\nTruncated: |\Z)', text, re.S)
    return match.group(1) if match else ''


class IdentityBeforeTopicDetailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='companion-lift-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.vault = root / 'vault'
        (self.vault / COMPANION).mkdir(parents=True)
        self.store = evaluator.load_runtime().MemoryStore(root / 'runtime', self.vault)
        self.addCleanup(lambda: evaluator.close_store(self.store))

    def seed(self, threads):
        bodies = {
            'Core.md': filler('Kimlik', 1650, 'CORE'),
            'Soul.md': filler('Üslup', 1150, 'SOUL'),
            'Kurallar.md': filler('Kurallar', 2600, 'GRULE'),
            'Last-Session.md': '# Son\n\n## 2026-10-01 10:00 · deneme · abcd1234\n' + filler('Devir', 900, 'HAND'),
            'Threads.md': threads,
            'Journal.md': '# Journal\n\n## 2026-10-01\n' + filler('J', 100, 'JRN'),
        }
        for name, body in bodies.items():
            source = f'{COMPANION}/{name}'
            (self.vault / source).write_text(body, encoding='utf-8')
            self.store.ingest({'id': source, 'kind': 'note', 'status': 'active', 'text': body,
                              'source': source, 'updated_at': '2026-10-01T00:00:00Z'})

    def test_identity_is_whole_before_long_topic_history_takes_the_rest(self):
        # Threads without topic headings has no protected overview: its detail is optional.
        self.seed('# Threads\n\n## Active Threads\n' + ''.join(
            f'## 2026-10-{i + 1:02d} · Konu {i}\n' + filler('T', 450, f'THR{i}_') for i in range(11)))
        for harness in ('claude', 'codex'):
            for budget in (9000, 9500):
                with self.subTest(harness=harness, budget=budget):
                    text = companion.context(self.store, budget, 'synthetic-lift', harness)
                    self.assertLessEqual(len(text), budget)
                    self.assertIn('GRULE_END', text)  # rules whole
                    self.assertIn('HAND_END', text)  # newest handoff card whole
                    self.assertIn('CORE_END', text)  # whole identity, not equal shares with the history
                    self.assertIn('SOUL_END', text)
                    self.assertGreaterEqual(len(section(text, 'Threads.md')), 1500)  # history keeps most of its share

    def test_protected_topic_overview_is_not_given_up_for_identity(self):
        threads = '# Threads\n\n## Active Threads\n' + ''.join(
            f'### Thread: Konu {i}\n**Status:** active\n**Next:** ADIM_{i}.\n' + filler('T', 400, f'THR{i}_') for i in range(8))
        self.seed(threads)
        for budget in (6000, 9500, 12000):
            with self.subTest(budget=budget):
                text = companion.context(self.store, budget, 'synthetic-lift', 'claude')
                self.assertLessEqual(len(text), budget)
                self.assertIn('GRULE_END', text)
                self.assertIn('HAND_END', text)
                self.assertEqual([i for i in range(8) if f'ADIM_{i}.' not in text], [])


if __name__ == '__main__':
    unittest.main()
