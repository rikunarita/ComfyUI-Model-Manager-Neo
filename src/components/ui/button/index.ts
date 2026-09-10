import { cva } from 'class-variance-authority'
import { type VariantProps } from 'class-variance-authority'

export { default as Button } from './Button.vue'

export const buttonVariants = cva(
  // NOTE: `active:scale-[0.97]` must stay an arbitrary value — bare `scale-0.97`
  // is NOT a valid Tailwind v4 utility (bare scale values are percentages) and
  // would silently compile to nothing, killing the press animation.
  // eslint-disable-next-line tailwindcss/no-unnecessary-arbitrary-value
  "mm-transition inline-flex shrink-0 items-center justify-center gap-2 rounded-mm-ctl text-sm font-medium whitespace-nowrap focus-visible:ring-2 focus-visible:ring-mm-ring focus-visible:outline-none active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        /*
         * GLASS REDESIGN (push buttons):
         * - coloured buttons render as a translucent "skeleton" of their own
         *   colour (bg <color>/<opacity>) with a hairline border of the same
         *   colour and a shadow tinted with the lightened colour;
         * - neutral (grey) buttons render on a translucent foreground tint
         *   with a hairline border and a soft, density-matched glass shadow;
         *   every variant blurs its backdrop so the glass reads as glass.
         * Before this pass `default`/`destructive`/`secondary` were OPAQUE
         * fills and the variants carried no border at all, so native buttons
         * kept the browser's UA face + light outline (grey box, white ring).
         */
        default:
          'border border-mm-accent/30 bg-mm-accent/16 text-mm-accent shadow-mm-accent-1 backdrop-blur-md hover:border-mm-accent/50 hover:bg-mm-accent/26 hover:shadow-mm-accent-2',
        destructive:
          'border border-mm-danger/30 bg-mm-danger/14 text-mm-danger shadow-mm-danger-1 backdrop-blur-md hover:border-mm-danger/50 hover:bg-mm-danger/24 hover:shadow-mm-danger-2 focus-visible:ring-mm-danger/50',
        outline:
          'border border-mm-fg/15 bg-mm-fg/5 text-mm-fg shadow-mm-glass-1 backdrop-blur-md hover:border-mm-fg/25 hover:bg-mm-fg/10 hover:shadow-mm-glass-2',
        secondary:
          'border border-mm-fg/14 bg-mm-fg/9 text-mm-fg shadow-mm-glass-1 backdrop-blur-md hover:border-mm-fg/24 hover:bg-mm-fg/16 hover:shadow-mm-glass-2',
        ghost:
          'border border-mm-fg/10 bg-mm-fg/5 text-mm-fg shadow-mm-glass-1 backdrop-blur-md hover:border-mm-fg/20 hover:bg-mm-fg/12 hover:shadow-mm-glass-2',
        link: 'text-mm-accent underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2 has-[>svg]:px-3',
        xs: "h-6 gap-1 rounded-mm-ctl px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: 'h-8 gap-1.5 rounded-mm-ctl px-3 has-[>svg]:px-2.5',
        lg: 'h-10 rounded-mm-ctl px-6 has-[>svg]:px-4',
        icon: 'size-9',
        'icon-xs': "size-6 rounded-mm-ctl [&_svg:not([class*='size-'])]:size-3",
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
