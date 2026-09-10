import { cva } from 'class-variance-authority'
import { type VariantProps } from 'class-variance-authority'

export { default as Badge } from './Badge.vue'

export const badgeVariants = cva(
  'mm-transition inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold backdrop-blur-md focus:ring-2 focus:ring-mm-ring focus:outline-none',
  {
    variants: {
      variant: {
        default: 'border-mm-accent/30 bg-mm-accent/18 text-mm-accent shadow-mm-accent-1',
        secondary: 'border-mm-fg/12 bg-mm-fg/8 text-mm-fg shadow-mm-glass-1',
        destructive: 'border-mm-danger/30 bg-mm-danger/16 text-mm-danger shadow-mm-danger-1',
        outline: 'border-mm-fg/20 bg-mm-fg/5 text-mm-fg shadow-mm-glass-1',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export type BadgeVariants = VariantProps<typeof badgeVariants>
