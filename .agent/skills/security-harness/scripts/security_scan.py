#!/usr/bin/env python3
"""
범용 보안 하네스 스캐너 (Universal Security Harness Scanner)
============================================================
Antigravity Agent Skill 실행 백엔드.
프로젝트 타입을 자동 감지하고 OWASP Top 10 2025 기준으로 보안 점검을 수행합니다.

사용법:
    python .agent/skills/security-harness/scripts/security_scan.py
    python .agent/skills/security-harness/scripts/security_scan.py --json
    python .agent/skills/security-harness/scripts/security_scan.py --md
    python .agent/skills/security-harness/scripts/security_scan.py --severity HIGH
"""

import os
import re
import sys
import json
import subprocess
import fnmatch
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Optional

# ============================================================================
# 1. 데이터 모델
# ============================================================================

class Finding:
    """단일 보안 발견 사항"""
    def __init__(self, scanner_id: str, category: str, severity: str,
                 file: str = "", line: int = 0, preview: str = "",
                 owasp: str = "", fix_hint: str = ""):
        self.scanner_id = scanner_id
        self.category = category
        self.severity = severity      # HIGH, MEDIUM, LOW, INFO
        self.file = file
        self.line = line
        self.preview = preview
        self.owasp = owasp
        self.fix_hint = fix_hint

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


class ScanResult:
    """스캐너 하나의 결과"""
    def __init__(self, scanner_id: str, name: str, owasp: str = ""):
        self.scanner_id = scanner_id
        self.name = name
        self.owasp = owasp
        self.findings: list[Finding] = []
        self.skipped = False
        self.skip_reason = ""

    @property
    def passed(self) -> bool:
        return not self.findings and not self.skipped

    @property
    def failed(self) -> bool:
        return bool(self.findings)


# ============================================================================
# 2. 프로젝트 감지기
# ============================================================================

class ProjectDetector:
    """프로젝트 루트를 분석해서 타입·언어·프레임워크를 자동 감지"""

    def __init__(self, root: str):
        self.root = Path(root)
        self.types: set[str] = set()        # python, node, go, java, web, llm
        self.frameworks: set[str] = set()   # flask, django, fastapi, express, react, ...
        self.files: list[Path] = []
        self.ignore_patterns = self._load_security_ignore()
        self._detect()

    def _load_security_ignore(self) -> list[str]:
        """.securityignore 파일에서 무시 패턴 로드"""
        ignore_file = self.root / ".securityignore"
        patterns = []
        if ignore_file.exists():
            try:
                for line in ignore_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
            except Exception:
                pass
        return patterns

    def _is_ignored(self, path: Path) -> bool:
        """경로가 .securityignore 패턴에 매칭되는지 확인"""
        try:
            rel_path = str(path.relative_to(self.root))
        except ValueError:
            rel_path = str(path)

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
            if pattern.endswith("/") and rel_path.startswith(pattern):
                return True
            parts = rel_path.split(os.sep)
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        return False

    def _detect(self):
        """파일 구성 기반 프로젝트 타입 감지"""
        markers = {
            "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "setup.cfg"],
            "node": ["package.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"],
            "go": ["go.mod", "go.sum"],
            "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "rust": ["Cargo.toml"],
        }
        for ptype, files in markers.items():
            if any((self.root / f).exists() for f in files):
                self.types.add(ptype)

        # 확장자 기반 보조 감지
        ext_map = {".py": "python", ".js": "node", ".ts": "node", ".jsx": "node",
                   ".tsx": "node", ".go": "go", ".java": "java", ".rs": "rust"}
        for dirpath, dirnames, filenames in os.walk(self.root):
            # EXCLUDE_DIRS 및 .securityignore 반영 디렉토리 필터링
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not self._is_ignored(Path(dirpath) / d)]
            for f in filenames:
                p = Path(dirpath) / f
                if self._is_ignored(p):
                    continue
                if p.suffix in ext_map:
                    self.types.add(ext_map[p.suffix])
                if p.suffix in SCAN_EXTENSIONS:
                    self.files.append(p)

        # 웹 프레임워크 감지
        self._detect_frameworks()

        # LLM 프로젝트 감지
        self._detect_llm()

        # 최소 fallback
        if not self.types:
            self.types.add("generic")

    def _detect_frameworks(self):
        """주요 프레임워크 감지"""
        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                fw_map = {"react": "react", "next": "next", "vue": "vue", "express": "express",
                          "fastify": "fastify", "svelte": "svelte", "@angular/core": "angular"}
                for key, name in fw_map.items():
                    if key in deps:
                        self.frameworks.add(name)
                        self.types.add("web")
            except Exception:
                pass

        # Python 프레임워크
        for pyfile in (f for f in self.files if f.suffix == ".py"):
            try:
                content = pyfile.read_text(errors="ignore")[:5000]
                if "from flask" in content or "import flask" in content:
                    self.frameworks.add("flask")
                    self.types.add("web")
                if "from django" in content or "import django" in content:
                    self.frameworks.add("django")
                    self.types.add("web")
                if "from fastapi" in content or "import fastapi" in content:
                    self.frameworks.add("fastapi")
                    self.types.add("web")
            except Exception:
                continue

    def _detect_llm(self):
        """LLM/AI 에이전트 프로젝트 감지"""
        llm_indicators = [
            "ollama", "openai", "anthropic", "gemini", "langchain", "llama",
            "prompt", "chat_completion", "generate", "api.anthropic.com",
            "api.openai.com", "localhost:11434",
        ]
        for pyfile in (f for f in self.files if f.suffix == ".py"):
            try:
                content = pyfile.read_text(errors="ignore")[:8000].lower()
                if sum(1 for ind in llm_indicators if ind in content) >= 2:
                    self.types.add("llm")
                    break
            except Exception:
                continue

    @property
    def summary(self) -> str:
        parts = [t.upper() for t in sorted(self.types)]
        if self.frameworks:
            parts.append(f"({', '.join(sorted(self.frameworks))})")
        return " + ".join(parts)


# ============================================================================
# 3. 공통 설정
# ============================================================================

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv",
                ".agent", ".next", "dist", "build", ".tox", ".mypy_cache",
                ".pytest_cache", "target", "vendor", "coverage"}

SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rs",
                   ".rb", ".php", ".yml", ".yaml", ".json", ".toml", ".cfg",
                   ".ini", ".sh", ".command", ".md", ".html", ".env.example",
                   ".plist", ".xml", ".gradle", ".tf", ".hcl"}


# ============================================================================
# 4. 스캐너 베이스 클래스
# ============================================================================

class BaseScanner(ABC):
    """모든 보안 스캐너의 기반 클래스"""

    scanner_id: str = "S00"
    name: str = "Base"
    owasp: str = ""
    applies_to: set[str] = {"generic"}   # 어떤 프로젝트 타입에 활성화되는지

    def __init__(self, root: str, detector: ProjectDetector):
        self.root = root
        self.detector = detector
        self.result = ScanResult(self.scanner_id, self.name, self.owasp)

    def should_run(self) -> bool:
        """이 스캐너가 현재 프로젝트에 적용되는지 판단"""
        if "all" in self.applies_to:
            return True
        return bool(self.applies_to & self.detector.types)

    @abstractmethod
    def scan(self) -> ScanResult:
        pass

    def add(self, category: str, severity: str, file: str = "",
            line: int = 0, preview: str = "", fix_hint: str = ""):
        """발견 사항 추가 (비밀값 자동 마스킹)"""
        masked = self._mask_secrets(preview)
        self.result.findings.append(Finding(
            scanner_id=self.scanner_id, category=category,
            severity=severity, file=file, line=line,
            preview=masked[:150], owasp=self.owasp, fix_hint=fix_hint,
        ))

    def scan_patterns(self, files: list[Path], patterns: list[tuple]) -> list[tuple]:
        """파일 목록에서 패턴 매칭 수행"""
        hits = []
        comment_prefixes = ('#', '//', '/*', '*', '<!--')
        for filepath in files:
            try:
                # 10MB 초과 대용량 파일 스킵
                if filepath.stat().st_size > 10 * 1024 * 1024:
                    continue
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                # ReDoS 방지를 위해 2000자 초과 긴 라인 스킵
                if len(line) > 2000:
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                # 인라인 무시 주석 검사
                line_lower = stripped.lower()
                if any(kw in line_lower for kw in ["nosec", "ignore-security", "security-ignore"]):
                    continue
                # S01, S02 스캐너를 제외하고는 주석 처리된 줄은 분석 스킵
                if self.scanner_id not in ("S01", "S02"):
                    if stripped.startswith(comment_prefixes):
                        continue
                for name, pattern, severity in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        rel_path = str(filepath.relative_to(self.root))
                        hits.append((name, severity, rel_path, line_num, stripped))
        return hits

    @staticmethod
    def _mask_secrets(text: str) -> str:
        """비밀값으로 보이는 긴 문자열을 마스킹"""
        return re.sub(r"[A-Za-z0-9+/=_-]{12,}", "****", text) if text else ""


# ============================================================================
# 5. 개별 스캐너 구현
# ============================================================================

class S01_SecretScanner(BaseScanner):
    scanner_id = "S01"
    name = "하드코딩 비밀값 (Hardcoded Secrets)"
    applies_to = {"all"}

    PATTERNS = [
        # 토큰·키 형태
        ("텔레그램 봇 토큰",     r"[0-9]{8,10}:[A-Za-z0-9_-]{35,}", "HIGH"),
        ("OpenAI API 키",        r"sk-[A-Za-z0-9]{20,}", "HIGH"),
        ("Anthropic API 키",     r"sk-ant-[A-Za-z0-9]{20,}", "HIGH"),
        ("AWS 액세스 키",        r"AKIA[0-9A-Z]{16}", "HIGH"),
        ("GCP 서비스 계정",      r'"private_key_id"\s*:\s*"[a-f0-9]{30,}"', "HIGH"),
        ("GitHub 토큰",          r"gh[ps]_[A-Za-z0-9_]{36,}", "HIGH"),
        ("Stripe 키",            r"sk_live_[A-Za-z0-9]{24,}", "HIGH"),
        ("Slack 토큰",           r"xox[baprs]-[A-Za-z0-9-]{10,}", "HIGH"),
        # 일반 할당 패턴
        ("비밀값 직접 할당",     r"""(?:api[_-]?key|secret|token|password|passwd|credentials?)\s*[=:]\s*['"][A-Za-z0-9+/=_.-]{16,}['"]""", "MEDIUM"),
        ("Bearer 토큰 하드코딩", r"""['"]Bearer\s+[A-Za-z0-9+/=_.-]{20,}['"]""", "MEDIUM"),
        ("Private Key 블록",     r"-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----", "HIGH"),
        # DB 접속 문자열
        ("DB 접속 URI",          r"""(?:mysql|postgres|mongodb|redis)://[^\s'"]{10,}""", "HIGH"),
    ]

    def scan(self) -> ScanResult:
        hits = self.scan_patterns(self.detector.files, self.PATTERNS)
        for name, sev, file, line, preview in hits:
            # .example 파일·플레이스홀더 제외
            if file.endswith(".example") or any(
                kw in preview.lower() for kw in
                ["your_", "여기에", "입력", "example", "placeholder", "xxx", "changeme"]
            ):
                continue
            self.add(name, sev, file, line, preview,
                     fix_hint=".env 파일로 분리하고 os.getenv()로 불러오세요.")
        return self.result


class S02_PIIScanner(BaseScanner):
    scanner_id = "S02"
    name = "개인정보 / 경로 노출 (PII Disclosure)"
    applies_to = {"all"}

    PATTERNS = [
        ("macOS 사용자 경로",    r"/Users/[a-zA-Z0-9_.-]+/", "MEDIUM"),
        ("Linux 홈 경로",        r"/home/[a-zA-Z0-9_.-]+/", "LOW"),
        ("Windows 사용자 경로",  r"C:\\Users\\[a-zA-Z0-9_.-]+\\", "MEDIUM"),
        ("이메일 주소",          r"[a-zA-Z0-9._%+-]+@(?:gmail|naver|daum|kakao|hotmail|outlook)\.\w+", "MEDIUM"),
        ("한국 전화번호",        r"01[0-9]-[0-9]{3,4}-[0-9]{4}", "HIGH"),
        ("주민등록번호 패턴",    r"[0-9]{6}-[1-4][0-9]{6}", "HIGH"),
        ("IP 주소 (프라이빗 외)",r"\b(?!10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.)[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b", "LOW"),
    ]

    def scan(self) -> ScanResult:
        hits = self.scan_patterns(self.detector.files, self.PATTERNS)
        for name, sev, file, line, preview in hits:
            if file.endswith(".example") or "__PROJECT_DIR__" in preview:
                continue
            self.add(name, sev, file, line, preview,
                     fix_hint="환경변수 또는 플레이스홀더로 교체하세요.")
        return self.result


class S03_GitHygieneScanner(BaseScanner):
    scanner_id = "S03"
    name = "Git 위생 (Git Hygiene)"
    applies_to = {"all"}

    REQUIRED_IGNORES = {
        "all": [".env", "*.log", "__pycache__/", ".DS_Store"],
        "python": ["*.pyc", ".venv/", "venv/", "*.egg-info/"],
        "node": ["node_modules/", "dist/", ".env.local"],
        "java": ["*.class", "target/", "*.jar"],
        "go": ["vendor/"],
    }

    def scan(self) -> ScanResult:
        gitignore_path = Path(self.root) / ".gitignore"

        # .gitignore 존재 확인
        if not gitignore_path.exists():
            self.add(".gitignore 파일 누락", "HIGH", ".gitignore", fix_hint="프로젝트 루트에 .gitignore를 생성하세요.")
            return self.result

        content = gitignore_path.read_text()
        required = list(self.REQUIRED_IGNORES["all"])
        for ptype in self.detector.types:
            required.extend(self.REQUIRED_IGNORES.get(ptype, []))

        for item in required:
            if item not in content:
                sev = "HIGH" if item in (".env",) else "MEDIUM"
                self.add(f".gitignore 누락: {item}", sev, ".gitignore",
                         fix_hint=f"echo '{item}' >> .gitignore")

        # git 추적 중인 민감 파일
        try:
            result = subprocess.run(
                ["git", "ls-files"], capture_output=True, text=True,
                cwd=self.root, timeout=10
            )
            sensitive = [".env", "config.py", "secrets.json", ".pem", ".key"]
            for tracked in result.stdout.splitlines():
                if any(tracked == s or tracked.endswith(s) for s in sensitive):
                    if not tracked.endswith(".example"):
                        self.add(f"민감 파일 추적 중: {tracked}", "HIGH", tracked,
                                 fix_hint=f"git rm --cached {tracked}")
        except Exception:
            pass

        # 히스토리 내 비밀값 잔존
        try:
            result = subprocess.run(
                ["git", "log", "-p", "-30", "--all"],
                capture_output=True, text=True, cwd=self.root, timeout=30
            )
            critical_patterns = [
                ("텔레그램 토큰", r"[0-9]{8,10}:[A-Za-z0-9_-]{35,}"),
                ("AWS 키",        r"AKIA[0-9A-Z]{16}"),
                ("Private Key",   r"-----BEGIN.*PRIVATE KEY-----"),
            ]
            for name, pattern in critical_patterns:
                if re.search(pattern, result.stdout):
                    self.add(f"히스토리 잔존: {name}", "HIGH", "git history",
                             fix_hint="git filter-repo로 히스토리 정리 필요")
        except Exception:
            pass

        return self.result


class S04_DependencyScanner(BaseScanner):
    scanner_id = "S04"
    name = "의존성 관리 (Dependency Management)"
    owasp = "A06, A08"
    applies_to = {"all"}

    def scan(self) -> ScanResult:
        if "python" in self.detector.types:
            self._check_python()
        if "node" in self.detector.types:
            self._check_node()
        if "go" in self.detector.types:
            self._check_go()
        return self.result

    def _check_python(self):
        for name in ("requirements.txt", "requirements-dev.txt"):
            req_path = Path(self.root) / name
            if not req_path.exists():
                continue
            for ln, line in enumerate(req_path.read_text().splitlines(), 1):
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                if "==" not in line and ">=" not in line and "<" not in line:
                    self.add(f"버전 미고정: {line}", "MEDIUM", name, ln,
                             fix_hint=f"pip freeze | grep {line.split('[')[0]} 으로 버전 확인 후 == 고정")

    def _check_node(self):
        pkg = Path(self.root) / "package.json"
        lock_files = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"]
        if pkg.exists() and not any((Path(self.root) / l).exists() for l in lock_files):
            self.add("Lock 파일 없음", "MEDIUM", "package.json",
                     fix_hint="npm install 또는 yarn install로 lock 파일 생성")

    def _check_go(self):
        gosum = Path(self.root) / "go.sum"
        if (Path(self.root) / "go.mod").exists() and not gosum.exists():
            self.add("go.sum 없음", "MEDIUM", "go.mod",
                     fix_hint="go mod tidy 실행")


class S05_CodeInjectionScanner(BaseScanner):
    scanner_id = "S05"
    name = "코드 / 커맨드 인젝션 (Code Injection)"
    owasp = "A03"
    applies_to = {"all"}

    PYTHON_PATTERNS = [
        ("eval() 사용",          r"\beval\s*\(", "HIGH"),
        ("exec() 사용",          r"\bexec\s*\(", "HIGH"),
        ("pickle.load 사용",     r"\bpickle\.loads?\s*\(", "HIGH"),
        ("os.system 사용",       r"\bos\.system\s*\(", "HIGH"),
        ("os.popen 사용",        r"\bos\.popen\s*\(", "MEDIUM"),
        ("subprocess shell=True",r"subprocess\.(?:run|call|Popen)\s*\([^)]*shell\s*=\s*True", "HIGH"),
        ("yaml.load 미안전",     r"\byaml\.load\s*\([^)]*\)(?!.*Loader)", "MEDIUM"),
        ("__import__ 사용",      r"\b__import__\s*\(", "MEDIUM"),
        ("compile + exec",       r"\bcompile\s*\(.*\bexec\b", "HIGH"),
    ]

    JS_PATTERNS = [
        ("eval() 사용",          r"\beval\s*\(", "HIGH"),
        ("Function() 생성자",    r"\bnew\s+Function\s*\(", "HIGH"),
        ("child_process 비안전", r"(?:exec|execSync|spawn)\s*\([^)]*\$\{", "HIGH"),
        ("innerHTML 동적 할당",  r"\.innerHTML\s*=\s*(?!['\"<])", "MEDIUM"),
        ("document.write 사용",  r"\bdocument\.write\s*\(", "MEDIUM"),
    ]

    GO_PATTERNS = [
        ("os/exec 문자열 결합",  r'exec\.Command\s*\([^)]*\+', "HIGH"),
    ]

    def scan(self) -> ScanResult:
        py_files = [f for f in self.detector.files if f.suffix == ".py"]
        js_files = [f for f in self.detector.files if f.suffix in (".js", ".ts", ".jsx", ".tsx")]
        go_files = [f for f in self.detector.files if f.suffix == ".go"]

        for hits, patterns in [
            (self.scan_patterns(py_files, self.PYTHON_PATTERNS), self.PYTHON_PATTERNS),
            (self.scan_patterns(js_files, self.JS_PATTERNS), self.JS_PATTERNS),
            (self.scan_patterns(go_files, self.GO_PATTERNS), self.GO_PATTERNS),
        ]:
            for name, sev, file, line, preview in hits:
                self.add(name, sev, file, line, preview)
        return self.result


class S06_SQLInjectionScanner(BaseScanner):
    scanner_id = "S06"
    name = "SQL / NoSQL 인젝션 (SQL Injection)"
    owasp = "A03"
    applies_to = {"python", "node", "java", "go", "generic"}

    PYTHON_PATTERNS = [
        ("execute(f-string)",     r"""\.execute\s*\(\s*f['"]""", "HIGH"),
        ("execute(.format())",    r"""\.execute\s*\([^)]*\.format\s*\(""", "HIGH"),
        ("execute(% 포맷)",       r"""\.execute\s*\(\s*['"].*%s.*['"](?:\s*%)""", "MEDIUM"),
        ("execute(+ 문자열 결합)",r"""\.execute\s*\(\s*['"].*['"]\s*\+""", "HIGH"),
        ("raw SQL in ORM",        r"""\.raw\s*\(\s*f['"]""", "HIGH"),
    ]

    JS_PATTERNS = [
        ("query(템플릿 리터럴)",  r"""\.query\s*\(\s*`[^`]*\$\{""", "HIGH"),
        ("query(+ 문자열 결합)",  r"""\.query\s*\(\s*['"].*['"]\s*\+""", "HIGH"),
    ]

    def scan(self) -> ScanResult:
        py_files = [f for f in self.detector.files if f.suffix == ".py"]
        js_files = [f for f in self.detector.files if f.suffix in (".js", ".ts")]
        for name, sev, file, line, preview in self.scan_patterns(py_files, self.PYTHON_PATTERNS):
            self.add(name, sev, file, line, preview,
                     fix_hint="파라미터 바인딩(?) 사용: cursor.execute('SELECT * FROM t WHERE id=?', (id,))")
        for name, sev, file, line, preview in self.scan_patterns(js_files, self.JS_PATTERNS):
            self.add(name, sev, file, line, preview,
                     fix_hint="Parameterized query 사용: db.query('SELECT * FROM t WHERE id=$1', [id])")
        return self.result


class S07_XSSScanner(BaseScanner):
    scanner_id = "S07"
    name = "XSS (Cross-Site Scripting)"
    owasp = "A03"
    applies_to = {"web", "node"}

    PATTERNS = [
        ("innerHTML 동적 할당",       r"\.innerHTML\s*=\s*(?!['\"<])", "MEDIUM"),
        ("dangerouslySetInnerHTML",    r"dangerouslySetInnerHTML", "HIGH"),
        ("document.write",            r"\bdocument\.write\s*\(", "MEDIUM"),
        ("v-html (Vue)",              r"\bv-html\s*=", "MEDIUM"),
        ("{!! !!} (Blade/Laravel)",    r"\{!!\s*\$", "HIGH"),
        ("| safe (Jinja/Django)",      r"\|\s*safe\b", "MEDIUM"),
        ("mark_safe (Django)",         r"\bmark_safe\s*\(", "MEDIUM"),
        ("Markup() (Flask)",           r"\bMarkup\s*\(", "MEDIUM"),
        ("render_template_string",     r"\brender_template_string\s*\(", "HIGH"),
    ]

    def scan(self) -> ScanResult:
        web_files = [f for f in self.detector.files
                     if f.suffix in (".js", ".ts", ".jsx", ".tsx", ".html", ".vue", ".py", ".php")]
        for name, sev, file, line, preview in self.scan_patterns(web_files, self.PATTERNS):
            self.add(name, sev, file, line, preview,
                     fix_hint="사용자 입력은 반드시 이스케이프 처리 후 렌더링하세요.")
        return self.result


class S08_ConfigSecurityScanner(BaseScanner):
    scanner_id = "S08"
    name = "보안 설정 오류 (Security Misconfiguration)"
    owasp = "A05"
    applies_to = {"all"}

    PATTERNS = [
        ("DEBUG = True (프로덕션)",    r"\bDEBUG\s*=\s*True\b", "HIGH"),
        ("Flask debug=True",           r"\.run\s*\([^)]*debug\s*=\s*True", "HIGH"),
        ("CORS allow all",             r"""(?:allow_origins|CORS_ORIGINS?)\s*=\s*\[?\s*['"]\*['"]""", "HIGH"),
        ("CORS credentials + *",       r"Access-Control-Allow-Origin.*\*", "HIGH"),
        ("SSL verify=False",           r"\bverify\s*=\s*False\b", "HIGH"),
        ("HTTP (비암호화) 엔드포인트", r"""['"]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[^'"]+['"]""", "LOW"),
        ("약한 SECRET_KEY",            r"""SECRET_KEY\s*=\s*['"](?:secret|changeme|password|test|dev)['"i]""", "HIGH"),
        ("AllowAny 인증",              r"\bAllowAny\b", "LOW"),
        ("verbose 에러 노출",          r"\btraceback\.format_exc\s*\(\)|\.stack\b", "LOW"),
    ]

    def scan(self) -> ScanResult:
        for name, sev, file, line, preview in self.scan_patterns(self.detector.files, self.PATTERNS):
            self.add(name, sev, file, line, preview)
        return self.result


class S09_AuthScanner(BaseScanner):
    scanner_id = "S09"
    name = "인증 / 접근 제어 (Auth & Access Control)"
    owasp = "A01, A07"
    applies_to = {"web"}

    PATTERNS = [
        ("JWT 비밀 하드코딩",          r"""jwt\.(?:encode|decode|sign)\s*\([^)]*['"][A-Za-z0-9_-]{8,}['"]""", "HIGH"),
        ("bcrypt 라운드 부족",         r"\bbcrypt\.(?:hash|gensalt)\s*\([^)]*(?:rounds?|salt_rounds)\s*=\s*[1-7]\b", "MEDIUM"),
        ("MD5/SHA1 해싱 (비밀번호용)",r"""(?:md5|sha1)\s*\(.*(?:password|passwd|pw)""", "HIGH"),
        ("localStorage 토큰 저장",     r"localStorage\.setItem\s*\([^)]*(?:token|jwt|session|auth)", "MEDIUM"),
        ("하드코딩 관리자 계정",       r"""(?:admin_password|root_pass|default_password)\s*=\s*['"][^'"]+['"]""", "HIGH"),
        ("노출된 .env 경로",          r"""(?:sendFile|serve|static)\s*\([^)]*\.env""", "HIGH"),
    ]

    def scan(self) -> ScanResult:
        for name, sev, file, line, preview in self.scan_patterns(self.detector.files, self.PATTERNS):
            self.add(name, sev, file, line, preview)
        return self.result


class S10_SSRFScanner(BaseScanner):
    scanner_id = "S10"
    name = "SSRF (Server-Side Request Forgery)"
    owasp = "A10"
    applies_to = {"web", "python", "node"}

    PATTERNS = [
        ("사용자 입력 URL 직접 요청 (Python)", r"requests\.(?:get|post|put|delete)\s*\(\s*(?:url|user_|req\.|request\.)", "HIGH"),
        ("사용자 입력 URL 직접 요청 (JS)",     r"(?:fetch|axios\.(?:get|post))\s*\(\s*(?:url|user|req\.|request\.)", "HIGH"),
        ("urllib + 동적 URL",                  r"urllib\.request\.urlopen\s*\(\s*(?!['\"http])", "MEDIUM"),
        ("메타데이터 URL 접근 가능",           r"169\.254\.169\.254", "HIGH"),
        ("redirect 무제한",                    r"\.redirect\s*\(\s*(?:url|next|return|req\.|request\.)", "MEDIUM"),
    ]

    def scan(self) -> ScanResult:
        server_files = [f for f in self.detector.files if f.suffix in (".py", ".js", ".ts", ".go")]
        for name, sev, file, line, preview in self.scan_patterns(server_files, self.PATTERNS):
            self.add(name, sev, file, line, preview,
                     fix_hint="URL 화이트리스트 검증 후 요청하세요. 내부 IP 대역(10.x, 169.254.x)을 차단하세요.")
        return self.result


class S11_PromptInjectionScanner(BaseScanner):
    scanner_id = "S11"
    name = "프롬프트 인젝션 방어 (Prompt Injection)"
    owasp = "LLM01"
    applies_to = {"llm"}

    def scan(self) -> ScanResult:
        checks = {
            "외부 텍스트 정제 함수 존재": False,
            "구분자 위조 방어 (regex)": False,
            "nonce 동적 구분자": False,
            "방어 지침 문구": False,
        }

        for filepath in self.detector.files:
            if filepath.suffix != ".py":
                continue
            try:
                content = filepath.read_text(errors="ignore")
            except Exception:
                continue

            # 외부 입력 정제 함수
            if re.search(r"def\s+(?:clean|sanitize|escape)_(?:untrusted|external|user|input)", content):
                checks["외부 텍스트 정제 함수 존재"] = True
            # 구분자 방어
            if re.search(r"re\.sub.*(?:UNTRUSTED|BOUNDARY|DELIMITER|FENCE)", content, re.IGNORECASE):
                checks["구분자 위조 방어 (regex)"] = True
            # nonce
            if "token_hex" in content or "secrets." in content or "uuid" in content.lower():
                checks["nonce 동적 구분자"] = True
            # 방어 지침
            if any(kw in content for kw in ["인젝션 방어", "injection", "따르지 말", "ignore instruction"]):
                checks["방어 지침 문구"] = True

        for check_name, passed in checks.items():
            if not passed:
                self.add(check_name, "HIGH",
                         fix_hint="외부 데이터를 LLM에 넣기 전 구획화(nonce 구분자) + 정제 + 방어 지침 추가")

        return self.result


class S12_CryptoScanner(BaseScanner):
    scanner_id = "S12"
    name = "암호화 취약점 (Cryptographic Failures)"
    owasp = "A02"
    applies_to = {"web", "python", "node", "java"}

    PATTERNS = [
        ("MD5 사용",              r"\bmd5\b(?!sum|check)", "MEDIUM"),
        ("SHA-1 사용",            r"\bsha1\b|SHA-1", "MEDIUM"),
        ("DES/3DES 사용",         r"\b(?:DES|3DES|TripleDES)\b", "HIGH"),
        ("ECB 모드 사용",         r"\bECB\b|MODE_ECB", "HIGH"),
        ("Random (보안 부적합)",  r"\brandom\.(?:random|randint|choice)\s*\(.*(?:token|key|secret|password|salt|nonce)", "HIGH"),
        ("Math.random (보안용)",  r"\bMath\.random\s*\(\).*(?:token|key|secret|password|salt)", "HIGH"),
        ("약한 IV/Salt 크기",     r"(?:iv|salt|nonce)\s*=\s*(?:b?['\"](?:[A-Za-z0-9]{1,15})['\"])", "MEDIUM"),
    ]

    def scan(self) -> ScanResult:
        for name, sev, file, line, preview in self.scan_patterns(self.detector.files, self.PATTERNS):
            self.add(name, sev, file, line, preview,
                     fix_hint="SHA-256+, AES-GCM, secrets.token_hex() 등 안전한 대안을 사용하세요.")
        return self.result


# ============================================================================
# 6. 리포터
# ============================================================================

class Reporter:
    """스캔 결과를 다양한 형식으로 출력"""

    def __init__(self, project_name: str, project_type: str, results: list[ScanResult]):
        self.project_name = project_name
        self.project_type = project_type
        self.results = results
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def console(self, severity_filter: Optional[str] = None):
        """터미널 출력"""
        print(f"\n🛡️  Security Harness Scan ({self.timestamp})")
        print(f"📁 Project: {self.project_name} | Type: {self.project_type}")
        print("=" * 64)

        total_findings = 0
        failed_cats = 0

        for r in self.results:
            if r.skipped:
                print(f"[{r.scanner_id}] {r.name}: ⏭️  SKIP ({r.skip_reason})")
                print()
                continue

            filtered = r.findings
            if severity_filter:
                levels = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
                min_level = levels.get(severity_filter.upper(), 0)
                filtered = [f for f in r.findings if levels.get(f.severity, 0) >= min_level]

            status = "✅ PASS" if not filtered else "❌ FAIL"
            owasp_tag = f" [{r.owasp}]" if r.owasp else ""
            print(f"[{r.scanner_id}] {r.name}{owasp_tag}: {status} ({len(filtered)}건)")

            if filtered:
                failed_cats += 1
                total_findings += len(filtered)
                for f in filtered[:7]:
                    icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(f.severity, "ℹ️")
                    if f.file:
                        loc = f"{f.file}:{f.line}" if f.line else f.file
                        print(f"   {icon} [{f.severity}] {loc} — {f.category}")
                        if f.preview:
                            print(f"      └ {f.preview[:100]}")
                    else:
                        print(f"   {icon} [{f.severity}] {f.category}")
                    if f.fix_hint:
                        print(f"      💡 {f.fix_hint}")
                if len(filtered) > 7:
                    print(f"   ... 외 {len(filtered) - 7}건")
            print()

        print("=" * 64)
        if failed_cats == 0:
            print("🎉 전체 통과 — 보안 취약점이 발견되지 않았습니다.")
        else:
            print(f"⚠️  {failed_cats}개 카테고리에서 총 {total_findings}건의 보안 이슈 발견.")
        print()
        return failed_cats

    def to_json(self) -> str:
        """JSON 출력 (CI/CD용)"""
        data = {
            "timestamp": self.timestamp,
            "project": self.project_name,
            "type": self.project_type,
            "results": [],
            "summary": {"total_findings": 0, "failed_categories": 0},
        }
        for r in self.results:
            entry = {
                "id": r.scanner_id, "name": r.name, "owasp": r.owasp,
                "passed": r.passed, "skipped": r.skipped,
                "findings": [f.to_dict() for f in r.findings],
            }
            data["results"].append(entry)
            if r.failed:
                data["summary"]["failed_categories"] += 1
                data["summary"]["total_findings"] += len(r.findings)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        """Markdown 리포트"""
        lines = [
            f"# 🛡️ Security Harness Scan Report",
            f"",
            f"- **일시**: {self.timestamp}",
            f"- **프로젝트**: {self.project_name}",
            f"- **타입**: {self.project_type}",
            f"",
            f"| ID | 카테고리 | OWASP | 상태 | 발견 |",
            f"|:---|:---------|:------|:-----|:-----|",
        ]
        for r in self.results:
            status = "⏭️ SKIP" if r.skipped else ("✅ PASS" if r.passed else "❌ FAIL")
            owasp = r.owasp or "—"
            count = len(r.findings) if not r.skipped else "—"
            lines.append(f"| {r.scanner_id} | {r.name} | {owasp} | {status} | {count} |")

        # 상세 내역
        for r in self.results:
            if not r.findings:
                continue
            lines.extend(["", f"## {r.scanner_id}: {r.name}", ""])
            for f in r.findings:
                loc = f"{f.file}:{f.line}" if f.file else ""
                lines.append(f"- **[{f.severity}]** {f.category} — `{loc}`")
                if f.preview:
                    lines.append(f"  - `{f.preview[:80]}`")
                if f.fix_hint:
                    lines.append(f"  - 💡 {f.fix_hint}")

        return "\n".join(lines)


# ============================================================================
# 7. 메인 오케스트레이터
# ============================================================================

ALL_SCANNERS = [
    S01_SecretScanner,
    S02_PIIScanner,
    S03_GitHygieneScanner,
    S04_DependencyScanner,
    S05_CodeInjectionScanner,
    S06_SQLInjectionScanner,
    S07_XSSScanner,
    S08_ConfigSecurityScanner,
    S09_AuthScanner,
    S10_SSRFScanner,
    S11_PromptInjectionScanner,
    S12_CryptoScanner,
]


def run_scan(root: str = ".", output: str = "console", severity: Optional[str] = None) -> int:
    """전체 보안 스캔 실행"""
    root = os.path.abspath(root)
    project_name = os.path.basename(root)

    # 프로젝트 감지
    detector = ProjectDetector(root)
    print(f"🔍 감지된 프로젝트 타입: {detector.summary}")
    print(f"📄 스캔 대상 파일: {len(detector.files)}개\n")

    # 스캐너 실행
    results: list[ScanResult] = []
    for ScannerClass in ALL_SCANNERS:
        scanner = ScannerClass(root, detector)
        if scanner.should_run():
            results.append(scanner.scan())
        else:
            result = ScanResult(scanner.scanner_id, scanner.name, scanner.owasp)
            result.skipped = True
            result.skip_reason = f"프로젝트 타입 미해당 ({scanner.applies_to})"
            results.append(result)

    # 리포트 출력
    reporter = Reporter(project_name, detector.summary, results)

    if output == "json":
        print(reporter.to_json())
    elif output == "md":
        md_path = Path(root) / f"security_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        md_path.write_text(reporter.to_markdown(), encoding="utf-8")
        print(f"📝 Markdown 리포트 저장: {md_path}")
        reporter.console(severity)
    else:
        reporter.console(severity)

    failed = sum(1 for r in results if r.failed)
    return failed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="범용 보안 하네스 스캐너")
    parser.add_argument("path", nargs="?", default=".", help="스캔할 프로젝트 경로")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--md", action="store_true", help="Markdown 리포트 생성")
    parser.add_argument("--severity", choices=["HIGH", "MEDIUM", "LOW", "INFO"],
                        help="최소 심각도 필터")
    args = parser.parse_args()

    fmt = "json" if args.json else ("md" if args.md else "console")
    exit_code = run_scan(args.path, fmt, args.severity)
    sys.exit(exit_code)
