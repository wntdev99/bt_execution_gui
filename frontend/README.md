# bt_execution_gui — frontend

Next.js 14 (App Router) + TypeScript + Tailwind + shadcn-style 컴포넌트 + Motion.
ROS2 Behavior Tree 운영 GUI 의 Phase D — 토스풍 + 운영 콘솔 디자인.

## 디자인 방향
- **Aesthetic**: 토스 (Toss) 의 신뢰감 + Linear/Vercel 의 정밀함 + ROS 운영 industrial signal
- **Typography**: Pretendard Variable (KR/EN) + Geist Mono (코드/숫자)
- **Color**: 흰색 base + signal red (emergency) / blue (active) / amber (dangerous) / green (success)
- **Motion**: staggered fade-in + ring pulse + slide-in timeline

## 1차 milestone (vertical slice)
- `/` Dashboard — 6 트리 카드 + 실행 상태 pulse
- `/single` — 트리 선택 → ParamForm → 실행 → WebSocket monitor
- 전역 EmergencyStopBar — 어디서나 1 클릭 접근

## 시작
```bash
# bt_web_bridge 가 :8000 에서 running 이어야 함
npm install
npm run gen-api-types   # OpenAPI → src/api/types.gen.ts (옵션, prerequisite)
npm run dev             # :3000
```

## 통신
- HTTP: `/api/*` → bt_web_bridge :8000 (next.config rewrites)
- WebSocket: `ws://localhost:8000/api/ws` (직접 연결, dev)
- Payload validator SSOT: `/api/trees/{id}/validate` (TS 재구현 금지 — handoff E-6)

## 디렉토리
```
src/
├── app/                  # App Router
│   ├── layout.tsx        # 전역 layout + EmergencyStopBar
│   ├── page.tsx          # / Dashboard
│   ├── single/page.tsx   # /single 단일 실행
│   └── globals.css
├── components/           # 재사용 UI
│   ├── EmergencyStopBar.tsx
│   ├── TreeCard.tsx
│   ├── TreeIcon.tsx
│   ├── ParamForm.tsx
│   ├── StatusPulse.tsx
│   └── ExecutionMonitor.tsx
├── hooks/
│   ├── useApi.ts
│   └── useWebSocket.ts
├── lib/
│   ├── utils.ts          # cn() / payload typed object helpers
│   └── types.ts          # 공통 타입 (manifest, ws event)
└── api/
    └── client.ts         # fetch wrapper
```
