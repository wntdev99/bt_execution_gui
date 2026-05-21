/**
 * Tree type 별 custom SVG icon.
 *
 * tree_id 의 키워드 매칭으로 분류 — Dock/Undock/Nav/Door/Elevator/기타.
 * 카드 좌상단 회색 + dangerous 일 때 amber 변형.
 */

interface Props {
  treeId: string;
  className?: string;
  size?: number;
}

function iconKind(treeId: string): 'dock' | 'undock' | 'nav' | 'door' | 'elevator' | 'generic' {
  const id = treeId.toLowerCase();
  if (id.includes('undock')) return 'undock';
  if (id.includes('dock')) return 'dock';
  if (id.includes('door') || id.includes('passdoor')) return 'door';
  if (id.includes('elevator') || id.includes('alighting') || id.includes('boarding')) {
    return 'elevator';
  }
  if (id.includes('nav') || id.includes('move')) return 'nav';
  return 'generic';
}

export function TreeIcon({ treeId, className = '', size = 28 }: Props) {
  const kind = iconKind(treeId);
  const props = {
    width: size,
    height: size,
    viewBox: '0 0 32 32',
    fill: 'none',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className,
  };

  switch (kind) {
    case 'dock':
      // anchor pointing down — staging + lock
      return (
        <svg {...props}>
          <circle cx="16" cy="9" r="3" stroke="currentColor" />
          <path d="M16 12v14" stroke="currentColor" />
          <path d="M10 18h12" stroke="currentColor" />
          <path d="M6 22c0 3 4 5 10 5s10-2 10-5" stroke="currentColor" />
        </svg>
      );
    case 'undock':
      // anchor pointing up — release
      return (
        <svg {...props}>
          <circle cx="16" cy="23" r="3" stroke="currentColor" />
          <path d="M16 20V6" stroke="currentColor" />
          <path d="M10 14h12" stroke="currentColor" />
          <path d="M6 10c0-3 4-5 10-5s10 2 10 5" stroke="currentColor" />
        </svg>
      );
    case 'nav':
      // navigation arrow
      return (
        <svg {...props}>
          <path d="M16 4l9 22-9-5-9 5 9-22z" stroke="currentColor" />
        </svg>
      );
    case 'door':
      // doorway with hinge
      return (
        <svg {...props}>
          <rect x="7" y="5" width="18" height="22" rx="1" stroke="currentColor" />
          <path d="M16 5v22" stroke="currentColor" />
          <circle cx="20" cy="16" r="1" fill="currentColor" />
        </svg>
      );
    case 'elevator':
      // elevator car with up/down chevrons
      return (
        <svg {...props}>
          <rect x="6" y="4" width="20" height="24" rx="2" stroke="currentColor" />
          <path d="M12 12l4-4 4 4" stroke="currentColor" />
          <path d="M12 20l4 4 4-4" stroke="currentColor" />
        </svg>
      );
    default:
      return (
        <svg {...props}>
          <circle cx="16" cy="16" r="10" stroke="currentColor" />
          <path d="M16 11v5l4 2" stroke="currentColor" />
        </svg>
      );
  }
}
