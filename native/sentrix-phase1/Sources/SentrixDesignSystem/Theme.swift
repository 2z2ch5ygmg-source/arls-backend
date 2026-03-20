import SwiftUI

public enum SentrixTheme {
    public enum Palette {
        public static let ink = Color(red: 0.07, green: 0.1, blue: 0.16)
        public static let surface = Color(red: 0.96, green: 0.97, blue: 0.98)
        public static let card = Color.white
        public static let border = Color(red: 0.84, green: 0.87, blue: 0.9)
        public static let accent = Color(red: 0.95, green: 0.4, blue: 0.18)
        public static let success = Color(red: 0.11, green: 0.62, blue: 0.32)
        public static let warning = Color(red: 0.91, green: 0.57, blue: 0.14)
        public static let danger = Color(red: 0.79, green: 0.22, blue: 0.23)
        public static let muted = Color(red: 0.42, green: 0.48, blue: 0.55)
    }

    public enum Spacing {
        public static let xxs: CGFloat = 4
        public static let xs: CGFloat = 8
        public static let sm: CGFloat = 12
        public static let md: CGFloat = 16
        public static let lg: CGFloat = 24
        public static let xl: CGFloat = 32
    }

    public enum Radius {
        public static let sm: CGFloat = 10
        public static let md: CGFloat = 16
        public static let lg: CGFloat = 24
    }

    public enum Typography {
        public static let pageTitle = Font.system(size: 30, weight: .bold, design: .rounded)
        public static let sectionTitle = Font.system(size: 20, weight: .semibold, design: .rounded)
        public static let cardTitle = Font.system(size: 18, weight: .semibold, design: .rounded)
        public static let body = Font.system(size: 16, weight: .regular, design: .default)
        public static let caption = Font.system(size: 13, weight: .regular, design: .default)
        public static let mono = Font.system(size: 13, weight: .regular, design: .monospaced)
    }
}

public extension View {
    func sentrixCardStyle() -> some View {
        self
            .padding(SentrixTheme.Spacing.md)
            .background(SentrixTheme.Palette.card)
            .overlay(
                RoundedRectangle(cornerRadius: SentrixTheme.Radius.md)
                    .stroke(SentrixTheme.Palette.border, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: SentrixTheme.Radius.md))
    }
}
