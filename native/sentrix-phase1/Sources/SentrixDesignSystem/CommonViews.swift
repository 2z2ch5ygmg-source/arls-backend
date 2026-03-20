import SentrixCore
import SwiftUI

public struct SystemSurfaceView: View {
    private let surface: SystemSurfaceModel
    private let action: (() -> Void)?

    public init(surface: SystemSurfaceModel, action: (() -> Void)? = nil) {
        self.surface = surface
        self.action = action
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: SentrixTheme.Spacing.sm) {
            Label(surface.title, systemImage: iconName)
                .font(SentrixTheme.Typography.cardTitle)
                .foregroundStyle(tintColor)
            Text(surface.message)
                .font(SentrixTheme.Typography.body)
                .foregroundStyle(SentrixTheme.Palette.ink)
            if let footnote = surface.footnote, !footnote.isEmpty {
                Text(footnote)
                    .font(SentrixTheme.Typography.caption)
                    .foregroundStyle(SentrixTheme.Palette.muted)
            }
            if let action, let actionKind = surface.actionKind {
                if actionKind == .retry {
                    Button(actionKind.title, action: action)
                        .buttonStyle(.borderedProminent)
                        .tint(SentrixTheme.Palette.accent)
                } else {
                    Button(actionKind.title, action: action)
                        .buttonStyle(.bordered)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .sentrixCardStyle()
    }

    private var iconName: String {
        switch surface.kind {
        case .info:
            return "info.circle.fill"
        case .warning:
            return "exclamationmark.circle.fill"
        case .error:
            return "exclamationmark.triangle.fill"
        case .blocked:
            return "hand.raised.fill"
        case .unauthorized:
            return "lock.fill"
        case .offline:
            return "wifi.slash"
        }
    }

    private var tintColor: Color {
        switch surface.kind {
        case .info:
            return SentrixTheme.Palette.accent
        case .warning:
            return SentrixTheme.Palette.warning
        case .error, .blocked:
            return SentrixTheme.Palette.danger
        case .unauthorized, .offline:
            return SentrixTheme.Palette.warning
        }
    }
}

public struct LoadingStateView: View {
    private let title: String
    private let message: String

    public init(title: String = "Loading", message: String) {
        self.title = title
        self.message = message
    }

    public var body: some View {
        VStack(spacing: SentrixTheme.Spacing.md) {
            ProgressView()
                .progressViewStyle(.circular)
            Text(title)
                .font(SentrixTheme.Typography.sectionTitle)
                .foregroundStyle(SentrixTheme.Palette.ink)
            Text(message)
                .font(SentrixTheme.Typography.body)
                .foregroundStyle(SentrixTheme.Palette.muted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(SentrixTheme.Spacing.xl)
        .background(SentrixTheme.Palette.surface.ignoresSafeArea())
    }
}

public struct EmptyStateView: View {
    private let title: String
    private let message: String

    public init(title: String, message: String) {
        self.title = title
        self.message = message
    }

    public var body: some View {
        SystemSurfaceView(
            surface: SystemSurfaceModel(kind: .info, title: title, message: message)
        )
    }
}

public struct ErrorStateView: View {
    private let title: String
    private let message: String
    private let retry: (() -> Void)?

    public init(title: String = "Request Failed", message: String, retry: (() -> Void)? = nil) {
        self.title = title
        self.message = message
        self.retry = retry
    }

    public var body: some View {
        SystemSurfaceView(
            surface: SystemSurfaceModel(
                kind: .error,
                title: title,
                message: message,
                actionKind: retry == nil ? nil : .retry
            ),
            action: retry
        )
    }
}

public struct UnauthorizedStateView: View {
    private let message: String
    private let action: () -> Void

    public init(message: String, action: @escaping () -> Void) {
        self.message = message
        self.action = action
    }

    public var body: some View {
        SystemSurfaceView(
            surface: SystemSurfaceModel(
                kind: .unauthorized,
                title: "Unauthorized",
                message: message,
                actionKind: .returnToLogin
            ),
            action: action
        )
    }
}

public struct OfflinePlaceholderView: View {
    private let message: String

    public init(message: String) {
        self.message = message
    }

    public var body: some View {
        SystemSurfaceView(
            surface: SystemSurfaceModel(
                kind: .offline,
                title: "Offline Placeholder",
                message: message,
                footnote: "Phase 1 does not reuse web PWA caching assumptions for native."
            )
        )
    }
}

public struct NoticeBannerView: View {
    private let notice: RuntimeNotice

    public init(notice: RuntimeNotice) {
        self.notice = notice
    }

    public var body: some View {
        HStack(alignment: .top, spacing: SentrixTheme.Spacing.sm) {
            Image(systemName: notice.kind == .readOnly ? "lock.doc.fill" : "person.text.rectangle.fill")
                .foregroundStyle(notice.kind == .readOnly ? SentrixTheme.Palette.danger : SentrixTheme.Palette.warning)
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
                Text(notice.title)
                    .font(SentrixTheme.Typography.cardTitle)
                    .foregroundStyle(SentrixTheme.Palette.ink)
                Text(notice.message)
                    .font(SentrixTheme.Typography.body)
                    .foregroundStyle(SentrixTheme.Palette.ink)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .sentrixCardStyle()
    }
}

public struct RuntimeNoticeGroupView: View {
    private let notices: [RuntimeNotice]

    public init(notices: [RuntimeNotice]) {
        self.notices = notices
    }

    public var body: some View {
        if notices.isEmpty {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.sm) {
                ForEach(notices) { notice in
                    NoticeBannerView(notice: notice)
                }
            }
        }
    }
}

public struct KeyValueRowView: View {
    private let key: String
    private let value: String
    private let monospaced: Bool

    public init(key: String, value: String, monospaced: Bool = false) {
        self.key = key
        self.value = value
        self.monospaced = monospaced
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
            Text(key)
                .font(SentrixTheme.Typography.caption)
                .foregroundStyle(SentrixTheme.Palette.muted)
            Text(value.isEmpty ? "-" : value)
                .font(monospaced ? SentrixTheme.Typography.mono : SentrixTheme.Typography.body)
                .foregroundStyle(SentrixTheme.Palette.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

public struct SectionCardView<Content: View>: View {
    private let title: String
    private let subtitle: String?
    private let content: Content

    public init(title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: SentrixTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: SentrixTheme.Spacing.xxs) {
                Text(title)
                    .font(SentrixTheme.Typography.cardTitle)
                    .foregroundStyle(SentrixTheme.Palette.ink)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(SentrixTheme.Typography.caption)
                        .foregroundStyle(SentrixTheme.Palette.muted)
                }
            }
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .sentrixCardStyle()
    }
}
