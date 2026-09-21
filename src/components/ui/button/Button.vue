<script lang="ts">
import { cva } from 'class-variance-authority'
import { type VariantProps } from 'class-variance-authority'
import { Primitive } from 'reka-ui'
import { type PrimitiveProps } from 'reka-ui'
import { type HTMLAttributes } from 'vue'
import { cn } from 'utils/cn'

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
        /*
         * CHROME ICON BUTTONS: the dialog top bar (layout / hidden-files /
         * refresh / download / upload, maximize, close) renders deliberately
         * larger than the rest of the chrome - 43.2 px (1.2× the 36 px
         * `icon` square, icons at 19.2 px) - so the primary window controls
         * are easy to hit. Model-detail action row (`icon-action`), toolbars
         * and the bulk bar stay on the shared 36 px square that matches the
         * 36 px inputs; the aliases keep call sites semantic.
         */
        'icon-header': 'size-[43.2px]',
        'icon-action': 'size-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

type ButtonVariants = VariantProps<typeof buttonVariants>
</script>

<script setup lang="ts">
interface Props extends PrimitiveProps {
  variant?: ButtonVariants['variant']
  size?: ButtonVariants['size']
  class?: HTMLAttributes['class']
  /**
   * Native button type.
   *
   * BUG FIX: this defaulted to the HTML built-in `"submit"`, which is not what
   * the PrimeVue Button this component replaced did — PrimeVue injects
   * `asAttrs: { type: 'button' }` for `as="BUTTON"`. Every icon button in
   * `ModelContent`'s `<form>` therefore submitted the form on click. The
   * visible casualty: pressing the pencil ("edit") in the model-detail dialog
   * set `editable = true` and then immediately ran the submit handler, which
   * saved and set `editable = false` again — the model editor could never be
   * opened, and the transient edit state wiped `formData.type` (the
   * "Directory" row vanished and any later save sent an empty type).
   */
  type?: 'button' | 'submit' | 'reset'
}

const props = withDefaults(defineProps<Props>(), {
  as: 'button',
  type: 'button',
})
</script>

<template>
  <Primitive
    :as="as"
    :as-child="asChild"
    :type="as === 'button' ? props.type : undefined"
    :class="cn(buttonVariants({ variant, size }), props.class)"
  >
    <slot />
  </Primitive>
</template>
