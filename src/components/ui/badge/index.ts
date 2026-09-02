import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Badge } from './Badge.vue'

export const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold mm-transition backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-mm-ring',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-mm-accent/80 text-mm-accent-fg shadow-mm-1',
        secondary: 'border-transparent bg-mm-surface/80 text-mm-fg',
        destructive: 'border-transparent bg-mm-danger/80 text-white shadow-mm-1',
        outline: 'border-mm-border-strong text-mm-fg bg-mm-bg/50',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export type BadgeVariants = VariantProps<typeof badgeVariants>
