# Kenya Audit Transparency - Frontend

A modern React/Next.js frontend for the Government Financial Transparency Audit Application.

## Features

### Home Dashboard

- **National Debt Panel**: Large debt figures with visual gauges and explanatory notes
- **Interactive Kenya Map**: Hoverable counties with auto-slideshow functionality
- **County Info Strip**: Selected county's budget, debt, and audit status with icons
- **Responsive Design**: Works on desktop, tablet, and mobile devices

### Design Principles

- **Big Numbers & Bold**: Important figures are prominently displayed
- **Jargon Explained**: Tooltips provide context for technical terms
- **No Raw Data Tables**: Clean, visual presentation at the dashboard level
- **Progressive Disclosure**: Detailed information available on demand

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Animation**: Framer Motion
- **Charts**: Recharts
- **Icons**: Lucide React + Heroicons
- **Maps**: React Simple Maps
- **Testing**: Jest + Testing Library

## Getting Started

### Prerequisites

- Node.js 18 or later
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.local.example .env.local

# Start development server
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to view the application.

### Environment Variables

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000      # Backend API URL
NEXT_PUBLIC_APP_NAME=Kenya Audit Transparency  # Application name
NEXT_PUBLIC_APP_VERSION=1.0.0                 # Version number
```

## Project Structure

```
frontend/
├── app/                    # Next.js App Router
│   ├── globals.css        # Global styles
│   ├── layout.tsx         # Root layout
│   └── page.tsx           # Home dashboard
├── components/            # React components
│   ├── dashboard/             # Home dashboard widgets (Summary, Debt, Budget, etc.)
│   ├── InteractiveKenyaMap.tsx # Interactive map
│   └── ...                    # See `components/` for the full tree
├── data/                  # Mock data and constants
│   └── mock-data.ts       # Kenya counties and national data
├── lib/                   # Utility functions
│   └── utils.ts           # Formatting and helper functions
├── types/                 # TypeScript definitions
│   └── index.ts           # Shared type definitions
└── public/                # Static assets
```

## Components

### dashboard/NationalDebtCard

Displays Kenya's total national debt with:

- Large, bold debt figure (KES X Trillion)
- Debt-to-GDP ratio with visual gauge
- Risk assessment (Low/Moderate/High)
- Domestic vs External debt breakdown
- Explanatory notes with tooltips

### InteractiveKenyaMap

Interactive map of Kenya with:

- County markers with hover effects
- Auto-slideshow through counties
- Click to select specific counties
- Popup with basic county information
- Responsive positioning

### dashboard/CountyDetailsPanel

County detail panel showing:

- Budget allocation with per-capita calculation
- Total debt and debt-to-budget ratio
- Audit status with color-coded indicators
- County GDP and economic metrics
- Call-to-action for full reports

## Styling

Uses Tailwind CSS with custom design system:

### Colors

- **Primary**: Blue tones for main actions and highlights
- **Success**: Green for positive metrics (clean audits, etc.)
- **Warning**: Yellow/orange for moderate risks
- **Danger**: Red for high risks and problems
- **Gray**: Neutral tones for backgrounds and text

### Typography

- **Large Numbers**: 4xl-6xl font sizes for key metrics
- **Medium Numbers**: 2xl-3xl for secondary figures
- **Inter Font**: Clean, modern typeface throughout

### Components

- **Cards**: Consistent white backgrounds with subtle shadows
- **Buttons**: Primary/secondary variants with hover states
- **Tooltips**: Dark overlays with helpful explanations

## Data Flow

1. **Mock Data**: Currently uses static data from `data/mock-data.ts`
2. **State Management**: React useState for selected county
3. **Props**: Parent-child communication for county selection
4. **API Integration**: Ready for backend API connection

## Development

### Available Scripts

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run start        # Start production server
npm run lint         # Run ESLint
npm test            # Run Jest tests
npm run test:watch  # Run tests in watch mode
```

### Adding New Components

1. Create component in `components/` directory
2. Use TypeScript with proper prop interfaces
3. Follow naming convention (PascalCase)
4. Include appropriate animations with Framer Motion
5. Add responsive design with Tailwind classes

### API Integration

To connect to the backend API:

1. Update `NEXT_PUBLIC_API_URL` in `.env.local`
2. Create API functions in `lib/api.ts`
3. Replace mock data with API calls
4. Add loading states and error handling

## Deployment

### Docker

```bash
# Build image
docker build -t audit-app-frontend .

# Run container
docker run -p 3000:3000 audit-app-frontend
```

### Vercel (Recommended)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

### Environment Variables for Production

Set these in your deployment platform:

- `NEXT_PUBLIC_API_URL`: Production API URL
- `NEXT_PUBLIC_APP_NAME`: Application name
- `NEXT_PUBLIC_APP_VERSION`: Current version

## Contributing

1. Follow the existing code style
2. Write tests for new components
3. Use TypeScript for type safety
4. Ensure responsive design
5. Add JSDoc comments for complex functions

## License

This project is part of the Government Financial Transparency Audit Application.
