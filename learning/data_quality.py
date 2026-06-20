# 데이터 출처/품질 게이트. 외부 데이터는 "값"이 아니라 "값+출처상태"로 흐른다.
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DataStatus(str, Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    UNAVAILABLE = "UNAVAILABLE"   # 수집 실패 → 값 없음 (가짜 생성 금지)


@dataclass
class Provenance:
    status: DataStatus
    source: str
    value: Any = None
    detail: str = ""

    @property
    def is_usable(self) -> bool:
        return self.status in (DataStatus.LIVE, DataStatus.CACHED) and self.value is not None

    @classmethod
    def live(cls, source: str, value: Any) -> Provenance:
        return cls(DataStatus.LIVE, source, value)

    @classmethod
    def unavailable(cls, source: str, detail: str = "") -> Provenance:
        return cls(DataStatus.UNAVAILABLE, source, None, detail)


@dataclass
class ReportQuality:
    sources: Dict[str, DataStatus] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)

    def record(self, prov: Provenance, critical: bool = False):
        self.sources[prov.source] = prov.status
        if not prov.is_usable:
            self.missing.append(prov.source)
            if critical:
                self.missing.append(f"CRITICAL:{prov.source}")

    @property
    def llm_available(self) -> bool:
        return not any(m.startswith("CRITICAL:") for m in self.missing)

    @property
    def is_degraded(self) -> bool:
        return not self.llm_available

    def banner(self) -> str:
        if not self.missing:
            return ""
        miss = ", ".join(sorted(set(m.replace("CRITICAL:", "") for m in self.missing)))
        return ("> ⚠️ **데이터 품질 경고 (DEGRADED)**\n"
                f"> 수집 실패 소스: **{miss}**. 이 리포트는 데이터가 누락됐고 **학습에서 제외**됩니다. "
                "수치를 신뢰하지 마십시오.\n")
