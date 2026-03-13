# 국내 증권사 API 비교 분석

> AI 자율 트레이딩 프로젝트를 위한 증권사 Open API 비교 (2025-2026 기준)

---

## 요약 비교표

| 항목 | 한국투자증권 (KIS) | LS증권 (eBest) | 키움증권 | NH투자증권 | 대신증권 |
|------|-------------------|----------------|----------|-----------|---------|
| **API 타입** | REST + WebSocket | REST + WebSocket (신규) / xingAPI COM/DLL (레거시) | REST (신규) / OCX (레거시) | DLL only | COM (CYBOS Plus) |
| **OS 독립성** | O (Linux/Mac/Windows) | O (REST) / X (xingAPI) | O (REST) / X (OCX) | X (Windows only) | X (Windows only) |
| **Python 지원** | 우수 (공식 + 커뮤니티) | 양호 (REST) / 보통 (xingAPI) | 양호 (REST) / 보통 (OCX+PyQt5) | 미흡 (C++ 중심) | 보통 (32bit Python 필요) |
| **모의투자** | O | O | O | O | O |
| **실시간 시세** | WebSocket (41종목/세션) | WebSocket (wss:9443) | WebSocket (REST API) | DLL 콜백 | COM 이벤트 |
| **Rate Limit** | 초당 20건 (REST) | 미공개 (추정 초당 10-20건) | 미공개 | 미공개 | 미공개 |
| **인증 방식** | OAuth (access_token) | Token (APP Key/Secret) | IP 화이트리스트 + Token | 모듈 인증 | HTS 로그인 필수 |
| **HTS 로그인 필요** | X | X (REST) / O (xingAPI) | X (REST) / O (OCX) | O | O |
| **async 친화도** | 높음 | 높음 (REST) | 높음 (REST) | 낮음 | 낮음 |
| **AI 자동매매 적합도** | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★☆☆☆ | ★★☆☆☆ |

---

## 1. 한국투자증권 (KIS) Open API

### 개요
- 2022년 4월 국내 최초 REST API 방식 오픈 API 출시
- 개발자 센터: https://apiportal.koreainvestment.com
- 공식 GitHub: https://github.com/koreainvestment/open-trading-api

### API 구조
| 구분 | 방식 | 용도 |
|------|------|------|
| 조회/주문 | REST API (HTTPS) | 계좌조회, 시세조회, 주문 |
| 실시간 | WebSocket (WSS) | 실시간 체결가, 호가, 체결통보 |
| 인증 | OAuth 2.0 | access_token (다음날 07시 만료) |

### 지원 시장
| 시장 | 지원 | 비고 |
|------|------|------|
| 국내 주식 (KOSPI/KOSDAQ) | O | 현물, ETF, ETN, ELW |
| 국내 선물/옵션 | O | KOSPI200 선물/옵션 등 |
| 해외 주식 | O | 미국, 일본, 중국, 홍콩 등 |
| 해외 선물/옵션 | O | 글로벌 선물/옵션 |
| 채권 | O | 상장채권 |
| 암호화폐 | X | 별도 거래소 API 필요 |

### Rate Limit
- REST API: **초당 20건** (슬라이딩 윈도우 방식)
- WebSocket: **세션당 41종목** 구독 가능
- 다중 세션/계좌로 확장 가능

### Python 생태계
| 라이브러리 | 타입 | 특징 |
|-----------|------|------|
| `python-kis` (Soju06) | 커뮤니티 | REST 기반, 타입 힌팅 100%, WebSocket 자동 재연결, GC 연동 |
| `pykis` (pjueon) | 커뮤니티 | 간결한 래퍼 |
| `mojito` | 커뮤니티 | 기존 프로젝트에서 사용 중 |
| 공식 샘플 코드 | 공식 | LLM/AI 환경 연동 예제 포함 |

### 장점
- **OS 독립적**: Linux 서버에서 운영 가능 (Docker/Cloud 배포 용이)
- **HTS 로그인 불필요**: API Key만으로 인증
- **Python async 친화적**: `python-kis`가 asyncio, WebSocket 완벽 지원
- **공식 AI/LLM 연동 지원**: ChatGPT, Claude 등과의 연동 예제 제공
- **가장 넓은 시장 커버리지**: 국내외 주식 + 선물옵션 + 채권
- **활발한 커뮤니티**: WikiDocs 가이드, 블로그, GitHub 프로젝트 다수

### 단점
- WebSocket 세션당 41종목 제한 (다중 계좌로 우회 필요)
- 슬라이딩 윈도우 방식 rate limit으로 burst 요청 시 제한 가능
- 토큰 만료 시간이 다음날 07시로 고정 (자동 갱신 로직 필요)

---

## 2. LS증권 (구 eBest투자증권) Open API

### 개요
- 레거시 xingAPI (COM/DLL) + 신규 REST/WebSocket Open API 병행 제공
- 신규 Open API: https://openapi.ls-sec.co.kr
- 수수료가 타사 대비 저렴한 것이 강점

### API 구조
| 구분 | 방식 (신규) | 방식 (레거시) |
|------|------------|-------------|
| 조회/주문 | REST API (HTTPS) | COM/DLL (xingAPI) |
| 실시간 | WebSocket (wss://openapi.ls-sec.co.kr:9443) | COM 이벤트 |
| 모의투자 | WebSocket port 29443 | 별도 서버 |
| 인증 | APP Key/Secret Token | HTS 로그인 |

### 지원 시장
| 시장 | 지원 | 비고 |
|------|------|------|
| 국내 주식 | O | KOSPI/KOSDAQ |
| 국내 선물/옵션 | O | xingAPI 기반 자동매매 활발 |
| 해외 주식 | O | 미국 등 |
| 해외 선물 | O | 야간선물 포함 |
| 암호화폐 | X | - |

### Python 생태계
| 라이브러리 | 특징 |
|-----------|------|
| xingAPI Python 래퍼 (dongho-jung) | COM 기반, Windows 필수 |
| k-ebest-im | Node.js 라이브러리 (참고용) |
| 공식 REST 샘플 | Python websockets 모듈 예제 |

### 장점
- **REST + WebSocket 신규 API**: OS 독립적 개발 가능
- **선물/옵션 자동매매 커뮤니티 강세**: 파생상품 트레이더 선호
- **수수료 경쟁력**: 타사 대비 낮은 수수료
- **xingAPI + REST 선택 가능**: 레거시/신규 중 선택

### 단점
- 신규 REST API의 문서/커뮤니티가 KIS 대비 부족
- xingAPI는 Windows COM 의존 (Linux 불가)
- Python 전용 커뮤니티 라이브러리가 KIS 대비 적음

---

## 3. 키움증권 Open API

### 개요
- 국내 주식시장 점유율 1위, 개인 투자자 가장 많은 증권사
- 레거시 Open API+ (OCX) + 신규 REST API 병행
- 신규 REST API: https://openapi.kiwoom.com
- 레거시 Open API+: https://www.kiwoom.com (OCX 기반)

### API 구조
| 구분 | 방식 (REST 신규) | 방식 (레거시 OCX) |
|------|-----------------|-----------------|
| 조회/주문 | REST API | OCX 컨트롤 (PyQt5) |
| 실시간 | WebSocket | OCX 이벤트 |
| 인증 | IP 화이트리스트 + Token | HTS 로그인 |
| OS | 크로스플랫폼 | Windows only |

### 지원 시장
| 시장 | 지원 | 비고 |
|------|------|------|
| 국내 주식 | O | KOSPI/KOSDAQ |
| 국내 선물/옵션 | O | |
| 해외 주식 | 제한적 | REST API에서 확인 필요 |
| 조건검색 | O | 키움 고유 기능 |
| 암호화폐 | X | - |

### Python 생태계
| 라이브러리 | 타입 | 특징 |
|-----------|------|------|
| `koapy` (elbakramer) | 커뮤니티 | Open API+ 래퍼, CLI 포함 |
| `pykiwoom` | 커뮤니티 | PyQt5 기반 간편 래퍼 |
| `kiwoom-restful` | 커뮤니티 | REST API 래퍼 |
| `breadum/kiwoom` | 커뮤니티 | 심플 라이브러리 |

### 장점
- **가장 큰 커뮤니티**: WikiDocs 가이드, 도서, 블로그 매우 풍부
- **조건검색 연동**: 키움 HTS 조건검색 API 연동 가능 (레거시)
- **신규 REST API**: 크로스플랫폼 지원으로 발전 중
- **모의투자 상시 운영**: 언제든 Paper Trading 가능

### 단점
- **신규 REST API 안정성**: 비교적 최근 출시로 생태계 성숙도 낮음
- **레거시 OCX**: Windows + PyQt5 필수, 32bit 제한 있음
- **해외 주식 API**: KIS 대비 커버리지 제한적
- **IP 화이트리스트**: 서버 이동 시 재등록 필요

---

## 4. NH투자증권 QV API

### 개요
- QV Open API: DLL 기반 접속 모듈
- https://www.nhqv.com
- C++ 개발 중심, Python 직접 지원 미흡

### API 구조
| 구분 | 방식 |
|------|------|
| 조회/주문 | DLL 라이브러리 |
| 실시간 | DLL 콜백 |
| 인증 | 모듈 기반 |
| OS | Windows only (Visual Studio) |

### 지원 시장
| 시장 | 지원 |
|------|------|
| 국내 주식 | O |
| 국내 선물/옵션 | O |
| 해외 주식 | 제한적 |

### Python 생태계
- **공식 Python 지원 없음**: C++ (Visual Studio) 중심
- `qvopenapi-rs` (Rust 래퍼): 커뮤니티 비공식
- Python ctypes로 DLL 호출은 이론상 가능하나 비실용적

### 장점
- NH투자증권 기존 고객이면 계좌 활용 가능

### 단점
- **Python/Linux 지원 부재**: AI 자동매매에 부적합
- **문서/자료 극히 부족**: 진입장벽 높음
- **REST API 미제공**: 현대적 개발 방식 불가
- **커뮤니티 거의 없음**

---

## 5. 대신증권 CYBOS Plus / CreOn

### 개요
- CYBOS Plus: 레거시 COM 기반 API
- CreOn: 차세대 서비스 (CYBOS 후속, 신기능은 CreOn에만 적용)
- https://www.creontrade.com

### API 구조
| 구분 | 방식 |
|------|------|
| 조회/주문 | COM 라이브러리 |
| 실시간 | COM 이벤트 구독 |
| 인증 | CreOn HTS 로그인 필수 |
| OS | Windows only (32bit) |

### 지원 시장
| 시장 | 지원 |
|------|------|
| 국내 주식 | O |
| 국내 선물/옵션 | O |
| 해외 주식 | 제한적 |

### Python 생태계
| 라이브러리 | 특징 |
|-----------|------|
| CybosPlus Python 비공식 가이드 | cybosplus.github.io |
| `creon-api` (woojae-jang) | 커뮤니티 래퍼 |
| `Creon-Datareader` (gyusu) | 데이터 수집 특화 |
| `DaishinTradingBot` (sm0514sm) | 자동매매 봇 예제 |

### 장점
- **과거 데이터 수집에 강점**: OHLCV 데이터 대량 수집 용이
- **다양한 언어 지원**: VB, C#, C++, .NET, Python, Delphi
- **안정적**: 오래된 API로 검증됨

### 단점
- **32bit Python 필수**: Anaconda 32bit 가상환경 필요
- **CreOn HTS 상시 실행 필요**: 백그라운드 프로세스 필수
- **Windows 전용**: Linux/Docker 배포 불가
- **REST API 미제공**: 현대적 아키텍처 불가
- **asyncio 호환 불가**: COM 기반으로 async 패턴 사용 불가

---

## AI 자율 트레이딩 적합성 평가

### 평가 기준 및 점수 (5점 만점)

| 기준 | KIS | LS증권 | 키움 | NH투자 | 대신 |
|------|-----|--------|------|--------|------|
| Python 3.12+ async 지원 | 5 | 4 | 4 | 1 | 1 |
| Linux/Docker 배포 | 5 | 4 | 4 | 1 | 1 |
| 모의투자 지원 | 5 | 4 | 5 | 3 | 3 |
| 해외주식 커버리지 | 5 | 4 | 3 | 2 | 2 |
| 실시간 데이터 | 4 | 4 | 4 | 3 | 4 |
| 문서/커뮤니티 | 5 | 3 | 5 | 1 | 3 |
| 무인 운영 (HTS 불필요) | 5 | 5 | 5 | 1 | 1 |
| API 안정성/성숙도 | 5 | 3 | 3 | 3 | 5 |
| Rate Limit 여유 | 4 | 3 | 3 | 3 | 3 |
| **총점** | **43** | **34** | **36** | **18** | **23** |

---

## 결론: 프로젝트 추천

### 1순위: 한국투자증권 (KIS) Open API

**선정 사유:**
- 국내 유일 완전한 REST + WebSocket API (OS 독립)
- Python async 생태계 가장 성숙 (`python-kis`)
- HTS 없이 API Key만으로 완전 자동화 가능
- 국내/해외 주식 + 선물옵션 + 채권까지 최대 커버리지
- 공식적으로 AI/LLM 연동 지원 (ChatGPT, Claude 예제 제공)
- Docker/Cloud 환경 배포 가능

**구현 시 고려사항:**
- Rate Limit: 초당 20건 (슬라이딩 윈도우) -> throttling 미들웨어 필요
- WebSocket: 세션당 41종목 -> 다중 세션 관리 로직 필요
- Token: 매일 07시 만료 -> 자동 갱신 스케줄러 필요

### 2순위 (보조): 키움증권 REST API

**보조 활용 사유:**
- 국내 최대 커뮤니티/자료 (학습/디버깅 용이)
- 조건검색 기능 (종목 스크리닝 자동화)
- 신규 REST API가 성숙하면 대안으로 전환 가능

### 3순위 (대안): LS증권 Open API

**대안 사유:**
- REST + WebSocket 지원
- 수수료 경쟁력
- 선물/옵션 자동매매 커뮤니티 강세

### 제외: NH투자증권, 대신증권

**제외 사유:**
- Windows DLL/COM 종속 -> Linux 서버 배포 불가
- Python async 지원 불가
- HTS 상시 실행 필요 -> 무인 운영 부적합
- REST API 미제공 -> 현대적 마이크로서비스 아키텍처 불가

---

## 기존 프로젝트 아키텍처와의 정합성

현재 `08-investment-api-guide.md` 및 `16-external-apis.md`에서 이미 한국투자증권을 국내 주식 API로 선정하고 있으며, 이 분석 결과 해당 선택이 최적임을 확인.

### 기존 설정과 업데이트 필요 사항

| 항목 | 기존 | 업데이트 |
|------|------|---------|
| Python 패키지 | `mojito` | `python-kis` 검토 (async/타입힌팅 우수) |
| Rate Limit | 초당 20건 | 슬라이딩 윈도우 방식 확인, throttling 구현 필요 |
| WebSocket | 미언급 | 세션당 41종목, 다중 세션 전략 필요 |
| 해외 주식 | Alpaca (미국만) | KIS로 미국+아시아 통합 가능 (Alpaca 병행도 가능) |
| 선물/옵션 | 미포함 | KIS API로 국내외 선물/옵션 커버 가능 |

---

## 참고 링크

- [KIS Developers 포털](https://apiportal.koreainvestment.com/intro)
- [KIS 공식 GitHub](https://github.com/koreainvestment/open-trading-api)
- [python-kis (PyPI)](https://pypi.org/project/python-kis/)
- [python-kis (GitHub)](https://github.com/Soju06/python-kis)
- [LS증권 Open API](https://openapi.ls-sec.co.kr/about-openapi)
- [키움 REST API](https://openapi.kiwoom.com/)
- [키움 Open API+ 가이드 (WikiDocs)](https://wikidocs.net/book/1173)
- [증권사 API 비교 (알뜰송송)](https://mg.jnomy.com/whatis-diff-stock-open-api)
- [CYBOS Plus 비공식 Python 가이드](https://cybosplus.github.io/)
- [NH QV Open API](https://www.nhqv.com/WMDoc.action?viewPage=/guestGuide/trading/openAPI.jsp)
