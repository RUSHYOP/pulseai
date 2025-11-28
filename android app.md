# PulsAI Health Monitor

A comprehensive React Native mobile application built with Expo for proactive health monitoring.

## Features

✅ **User Authentication** - Email/password login and registration with OAuth support
✅ **Real-time Health Dashboard** - Live heart rate, SpO2 monitoring with visual gauges
✅ **Historical Trends** - Interactive charts showing health data over customizable time periods
✅ **Proactive Alerts** - Predictive and anomaly-based health notifications
✅ **Emergency SOS** - One-tap emergency alert to contacts
✅ **Emergency Contacts Management** - Add, edit, and call emergency contacts
✅ **Settings & Customization** - Configure alert thresholds and notification preferences
✅ **Offline Support** - Mock data mode for development and testing

## Tech Stack

- **Framework**: React Native with Expo
- **Language**: TypeScript
- **State Management**: Redux Toolkit
- **Navigation**: React Navigation (Stack & Bottom Tabs)
- **Data Visualization**: React Native Chart Kit
- **Storage**: AsyncStorage
- **UI Components**: Custom component library with consistent theming

## Project Structure

```
PulsAIHealthMonitor/
├── src/
│   ├── components/
│   │   ├── common/          # Reusable UI components
│   │   ├── health/          # Health-specific components
│   │   ├── charts/          # Chart components
│   │   ├── alerts/          # Alert components
│   │   └── emergency/       # Emergency components
│   ├── screens/
│   │   ├── auth/            # Login & Registration
│   │   ├── DashboardScreen.tsx
│   │   ├── TrendsScreen.tsx
│   │   ├── AlertsScreen.tsx
│   │   ├── ProfileScreen.tsx
│   │   ├── SettingsScreen.tsx
│   │   └── EmergencyContactsScreen.tsx
│   ├── navigation/          # Navigation configuration
│   ├── store/               # Redux store and slices
│   ├── services/            # API services
│   ├── utils/               # Utility functions
│   ├── theme/               # Theme and styling
│   ├── types/               # TypeScript types
│   ├── mocks/               # Mock data
│   ├── config/              # App configuration
│   └── App.tsx              # Main app component
├── assets/                  # Images and fonts
└── package.json
```

## Getting Started

### Prerequisites

- Node.js (v16 or higher)
- npm or yarn
- Expo CLI
- iOS Simulator (Mac only) or Android Emulator

### Installation

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Start the development server**:
   ```bash
   npm start
   ```

3. **Run on platform**:
   - iOS: Press `i` or run `npm run ios`
   - Android: Press `a` or run `npm run android`
   - Web: Press `w` or run `npm run web`

### Mock Data Mode

The app currently runs in **mock data mode**, which means:
- No real API backend is required
- Sample health data is generated automatically
- All authentication works with any email/password combination
- Perfect for development and testing

To connect to a real API later:
1. Update `USE_MOCK = false` in service files
2. Configure API base URL in `src/config/api.config.ts`
3. Implement actual API endpoints

## Key Features Breakdown

### 1. Dashboard
- Real-time health metrics (HR, SpO2)
- Circular gauges with color-coded status
- Current health state classification
- Activity level indicator
- Auto-refresh every 5 seconds
- Quick access SOS button

### 2. Trends
- Historical data visualization
- Multiple time ranges (24h, 7d, 30d)
- Separate charts for vitals and health score
- Interactive line charts
- Behavioral pattern insights

### 3. Alerts
- Filter by all/unread
- Alert severity indicators
- Push notification support (when configured)
- Alert acknowledgment
- Detailed alert information

### 4. Emergency
- Prominent SOS button with confirmation
- Emergency contacts management
- Quick call functionality
- Primary contact designation

### 5. Settings
- Configurable alert thresholds
- Notification preferences
- Dark mode toggle (ready for implementation)
- Sound and vibration controls

## Configuration

### Alert Thresholds
Customize health monitoring thresholds in the Settings screen:
- Low SpO2 threshold (default: 92%)
- High heart rate (default: 120 bpm)
- Low heart rate (default: 50 bpm)

### Notification Preferences
Control which alerts you receive:
- Predictive alerts (LSTM forecasting)
- Anomaly detection alerts
- Emergency alerts
- System notifications

## Future Enhancements

- [ ] OAuth integration (Google, Apple Sign-In)
- [ ] Firebase Cloud Messaging for push notifications
- [ ] WebSocket for real-time data streaming
- [ ] Advanced behavioral pattern visualization
- [ ] Health data export
- [ ] Caregiver access mode
- [ ] Integration with wearable devices
- [ ] AI-powered health insights

## Testing

### Login Credentials (Mock Mode)
- Email: Any valid email format
- Password: Any password (8+ characters recommended)

Or use the pre-configured demo account:
- Email: demo@pulsai.health
- Password: password123

## Troubleshooting

### Common Issues

1. **Metro bundler issues**:
   ```bash
   npm start -- --clear
   ```

2. **Module not found errors**:
   ```bash
   rm -rf node_modules
   npm install
   ```

3. **iOS build issues**:
   ```bash
   cd ios && pod install && cd ..
   ```

## License

MIT License - Feel free to use this project for learning and development.

## Support

For issues or questions, please open an issue in the repository.

---

Built with ❤️ using React Native and Expo
