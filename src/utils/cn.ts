import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  // eslint-disable-next-line tailwindcss/no-custom-classname -- `inputs` is a rest parameter identifier, not a class name
  return twMerge(clsx(inputs))
}
