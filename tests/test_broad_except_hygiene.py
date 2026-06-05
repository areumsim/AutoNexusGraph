"""broad-except 위생 회귀 가드 — src/ + scripts/ + tests/.

R1~R10 누적 처리 결과 보존:
- bare `except:` (모든 예외 + KeyboardInterrupt 도 잡음) 절대 금지.
- `except Exception:` 은 반드시 `# noqa: BLE001 — <사유>` 동반.

목적은 silent swallow 의 신규 유입 차단. 사유가 명시되면 reviewer 가 의도를
검토 가능하고, `BLE001` 룰이 활성화되어 ruff/flake8 이 자동으로 잡아준다.

검사 범위: `src/` + `scripts/` + `tests/` 도 부분 적용.
- src/ 와 scripts/ 는 R8/R9/R10 처리 후 잔여 0.
- tests/ 는 본 라운드(2026-06-05) 7건 사유 명시 후 0. **예외 패턴**: `with
  pytest.raises(Exception)` 같이 raise 검증용은 본 가드의 `except` 패턴이
  아니라 자연 통과 (가드 무관).

예외:
- module docstring(`\"\"\" ... \"\"\"`) 안의 예제 코드 — 실제 실행되지 않음.
"""

from __future__ import annotations

import re
import tokenize
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (REPO / "src", REPO / "scripts", REPO / "tests")


def _iter_python_files():
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            yield p


def _code_lines(text: str) -> set[int]:
    """파일 텍스트에서 docstring / 주석이 아닌 '실제 코드' 라인 번호 set.

    tokenize 로 STRING 토큰 (docstring 포함) 의 라인을 제외 → docstring 안의
    예제 코드를 가드 대상에서 빼는 것이 목적. 일반 코드 라인의 trailing 주석은
    포함되어야 하므로 (noqa 사유 검사용) COMMENT 토큰은 제외 안 함.
    """
    code = set()
    skip = set()
    try:
        tokens = list(tokenize.tokenize(BytesIO(text.encode("utf-8")).readline))
    except tokenize.TokenizeError:
        # 토크나이즈 실패 시 보수적으로 모든 라인 코드 취급.
        return set(range(1, len(text.splitlines()) + 1))

    for tok in tokens:
        if tok.type == tokenize.STRING:
            # 멀티라인 STRING (docstring 후보) 의 모든 줄 skip.
            start_line, _ = tok.start
            end_line, _ = tok.end
            for ln in range(start_line, end_line + 1):
                skip.add(ln)
        elif tok.type not in (tokenize.NEWLINE, tokenize.NL,
                                tokenize.INDENT, tokenize.DEDENT,
                                tokenize.ENCODING, tokenize.ENDMARKER,
                                tokenize.COMMENT):
            code.add(tok.start[0])

    return code - skip


def test_no_naked_except_clause():
    """`except:` (Exception 없는 완전 bare) 0건. KeyboardInterrupt 도 잡아 위험.

    trailing 주석 허용 — `except:  # noqa: E722` 같은 ruff 무력화도 fail.
    """
    pat = re.compile(r'^\s*except\s*:\s*(?:#.*)?$')
    violations: list[str] = []
    for p in _iter_python_files():
        text = p.read_text(encoding="utf-8")
        code_lines = _code_lines(text)
        for i, line in enumerate(text.splitlines(), 1):
            if i not in code_lines:
                continue
            if pat.match(line):
                violations.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:80]}")
    assert not violations, (
        "bare `except:` 발견 (KeyboardInterrupt 도 잡힘 — 절대 금지):\n"
        + "\n".join(violations[:10])
    )


def test_except_exception_has_noqa_with_reason():
    """`except Exception(...):` 은 반드시 `# noqa: BLE001 — <사유>` 동반.

    R8/R9 회귀 가드: silent swallow 가 신규 유입되는 것을 막는다. 정당한
    사용은 사유를 명시하면 통과 — 새 코드가 broad-except 를 쓰려면 reviewer 가
    이유를 볼 수 있어야 한다.
    """
    # except Exception 또는 except Exception as e — trailing 주석 검사.
    pat = re.compile(r'^\s*except\s+Exception(?:\s+as\s+\w+)?\s*:(.*)$')
    # 허용: `# noqa: BLE001 — <reason>` (em-dash 뒤 1자 이상)
    noqa_with_reason = re.compile(r'#\s*noqa:\s*BLE001\s+—\s*\S')

    violations: list[str] = []
    for p in _iter_python_files():
        text = p.read_text(encoding="utf-8")
        code_lines = _code_lines(text)
        for i, line in enumerate(text.splitlines(), 1):
            if i not in code_lines:
                continue
            m = pat.match(line)
            if not m:
                continue
            trailing = m.group(1)
            if not noqa_with_reason.search(trailing):
                violations.append(f"{p.relative_to(REPO)}:{i}: {line.strip()[:120]}")

    assert not violations, (
        "`except Exception:` 사유 미명시 발견 — `# noqa: BLE001 — <사유>` 강제:\n"
        + "\n".join(violations[:20])
    )


def test_noqa_ble001_reason_not_empty():
    """기존 `# noqa: BLE001 —` 사유가 빈 문자열이거나 너무 짧지 않은지.

    `— `(em-dash + space) 뒤에 최소 5자 이상 의미 있는 문구. 통과 회피용 빈
    사유 차단.
    """
    pat = re.compile(r'#\s*noqa:\s*BLE001\s+—\s*(.+?)\s*$')
    violations: list[str] = []
    for p in _iter_python_files():
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            m = pat.search(line)
            if not m:
                continue
            reason = m.group(1).strip()
            if len(reason) < 5:
                violations.append(f"{p.relative_to(REPO)}:{i}: reason={reason!r}")

    assert not violations, (
        "noqa BLE001 사유가 너무 짧음 (5자 미만):\n"
        + "\n".join(violations[:10])
    )
