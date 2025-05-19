import presetRemToPx from '@unocss/preset-rem-to-px'

import {
  defineConfig,
  presetAttributify,
  presetIcons,
  presetWind3,
  toEscapedSelector,
  transformerDirectives,
***REMOVED*** from 'unocss'


export default defineConfig({
  presets: [
    presetWind3(***REMOVED***,
    presetAttributify(***REMOVED***,
    presetIcons(***REMOVED***,
    presetRemToPx({
      baseFontSize: 4,
    ***REMOVED******REMOVED***,
  ],
  transformers: [
    transformerDirectives(***REMOVED***,
  ],
  theme: {
    colors: {
      primary: '#692ee6',
      success: '#52c41a',
      warning: '#fe7d18',
      danger: '#fa5555',
      info: '#909399',
      bgcolor: '#f2ecee',
    ***REMOVED***,
  ***REMOVED***,
  rules: [
    [
      'navbar-shadow', {
        'box-shadow': '0 1px 4px rgb(0 21 41 / 8%***REMOVED***',
      ***REMOVED***,
***REMOVED***,
    [
      /^wrapper-dialog-(.+***REMOVED***$/,
      ([, name], { rawSelector, theme ***REMOVED******REMOVED*** => {
        const themeColor = (theme as any***REMOVED***.colors
        const selector = toEscapedSelector(rawSelector***REMOVED***
        return `
          ${selector***REMOVED*** {
          ***REMOVED***
          ***REMOVED***
          ***REMOVED***
            overflow: hidden;
          ***REMOVED***
          ${selector***REMOVED*** .n-dialog__title {
            padding: var(--n-padding***REMOVED***;
          ***REMOVED***
          ${selector***REMOVED*** .n-dialog__content {
          ***REMOVED***
          ***REMOVED***
            min-height: 0;
          ***REMOVED***
***REMOVED***
      ***REMOVED***,
***REMOVED***,
  ],
***REMOVED******REMOVED***
