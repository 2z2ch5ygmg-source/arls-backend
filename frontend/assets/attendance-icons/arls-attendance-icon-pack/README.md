# ARLS Attendance Icon Pack

출퇴근 탭 UI에서 사용하는 SVG 아이콘팩입니다.

## 구성

- `svg/` : 개별 SVG 아이콘
- `arls-attendance-sprite.svg` : `<symbol>` 기반 SVG sprite
- `manifest.json` : 아이콘명, 한글 용도, 카테고리 정보
- `preview.html` : 전체 아이콘 미리보기

## 사용 방식

개별 SVG는 모두 `currentColor` 기반입니다. CSS에서 색상을 제어하면 됩니다.

```html
<img src="./svg/late.svg" alt="지각">
```

인라인 SVG 또는 sprite로 사용할 때:

```html
<svg class="icon icon-orange">
  <use href="./arls-attendance-sprite.svg#arls-late"></use>
</svg>
```

```css
.icon {
  width: 24px;
  height: 24px;
  color: #111827;
}

.icon-orange {
  color: #ff5a00;
}

.icon-danger {
  color: #ef4444;
}

.icon-muted {
  color: #9ca3af;
}
```

## 상태 색상 권장값

- 기본 아이콘: `#111827`
- 브랜드/활성: `#ff5a00`
- 정상: `#16a34a`
- 지각/조퇴: `#ff5a00`
- 미출근/미퇴근: `#ef4444`
- 휴가/예정/비활성: `#9ca3af`
