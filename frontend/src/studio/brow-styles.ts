import { DEFAULT_BROWS, type BrowAsset } from './brows'

export type BrowStyle = {
  id: string
  label: string
  asset: BrowAsset
  width: number
  thickness: number
}
export function makeBrowStyles(assets: readonly BrowAsset[]): BrowStyle[] {
  return assets.map(asset => ({ id: asset.id, label: asset.label, asset, width: DEFAULT_BROWS.width, thickness: DEFAULT_BROWS.thickness }))
}
