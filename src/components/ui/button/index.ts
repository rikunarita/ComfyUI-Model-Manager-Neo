import type { VariantProps } from 'class-variance-authority'
import { cva } from 'class-variance-authority'

export { default as Button } from './Button.vue'

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-mm-ctl text-sm font-medium mm-transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mm-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*=\'size-\'])]:size-4 shrink-0 [&_svg]:shrink-0 active:scale-[0.97]',
  {
    variants: {
      variant: {
        default:
          'bg-mm-accent text-mm-accent-fg shadow-mm-1 hover:bg-mm-accent/90 hover:shadow-mm-2',
        destructive:
          'bg-mm-danger text-white shadow-mm-1 hover:bg-mm-danger/90 focus-visible:ring-mm-danger/50',
        outline:
          'border border-mm-border-strong bg-transparent shadow-mm-1 hover:bg-mm-surface-hover hover:text-mm-fg',
        secondary:
          'bg-mm-surface text-mm-fg shadow-mm-1 hover:bg-mm-surface-hover',
        ghost: 'hover:bg-mm-surface-hover hover:text-mm-fg',
        link: 'text-mm-accent underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2 has-[>svg]:px-3',
        xs: 'h-6 gap-1 rounded-mm-ctl px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*=\'size-\'])]:size-3',
        sm: 'h-8 rounded-mm-ctl gap-1.5 px-3 has-[>svg]:px-2.5',
        lg: 'h-10 rounded-mm-ctl px-6 has-[>svg]:px-4',
        icon: 'size-9',
        'icon-xs': 'size-6 rounded-mm-ctl [&_svg:not([class*=\'size-\'])]:size-3',
        'icon-sm': 'size-8',
        'icon-lg': 'size-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export type ButtonVariants = VariantProps<typeof buttonVariants>
