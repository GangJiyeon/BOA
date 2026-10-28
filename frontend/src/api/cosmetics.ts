import { api } from './client'

export type MetricCode = 'moisture' | 'redness' | 'brightness' | 'trouble' | 'uniformity'
export type ProductCategory = 'moisturizer' | 'serum' | 'toner'

export type AnalysisMetricScore = {
  metric_code: MetricCode
  metric_name: string
  score: number
  category_name: string
  higher_is_better: boolean
}

export type PreviewRequest = {
  scores: (Record<Exclude<MetricCode, 'moisture'>, number> & { moisture: number | null }) | AnalysisMetricScore[]
  score_semantics?: 'photo_v1' | 'development_assumption'
  moisture_analysis_id?: number
  moisture_measurement_id?: string
  category: ProductCategory | null
  avoid_redness_triggers: boolean
  avoid_dryness_triggers?: boolean
  excluded_ingredients: string[]
  tie_group?: string
  tie_offset?: number
  snapshot_token?: string
}

export type RuleExplanation = {
  rule_code: string
  ingredient: string
  effect: string
  evidence_url: string
  evidence_summary: string
  limitations: string
  rationale: string
}

export type PreviewResponse = {
  hydration_policy?: { score_max?:number; normalized_score?:number; moisture_level?:number; moisture_level_label?:string; version:string; state:'low'|'normal'|'sufficient'|'unmeasured'; basis:'supplied_moisture_category'|'persisted_sensor_estimate'; estimation_version?:string; validation_level?:string; strategy:string; dryness_exclusion_enabled:boolean }
  sensor_auxiliary?: { measurement_id: string; experimental_index: number; applied: boolean } | null
  recommendation_mode?: 'improvement' | 'daily_care'
  daily_care_reason?: 'no_improvement_targets' | 'no_supported_matching_rules' | null
  recommendation_notice?: string
  ranking_basis?: string
  snapshot_token: string
  tie_groups: { key: string; total: number; next_offset: number | null }[]
  engine_version: string
  rule_version: string
  explanation_version?: string
  score_basis: string
  target_count: number
  scorable_target_count: number
  deferred_metrics: MetricCode[]
  assessments: { score_max?:number; moisture_level?:number; moisture_level_label?:string; code: MetricCode; name: string; score: number; category: string; needs_improvement: boolean }[]
  missing_metrics: MetricCode[]
  applied_exclusions: string[]
  exclusion_details: RuleExplanation[]
  recommendations: {
    rank: number
    product_id: number
    product_name: string
    brand_name: string
    category: ProductCategory
    image_url: string | null
    source_url: string | null
    sensor_auxiliary_bonus?: number
    sensor_auxiliary_ingredients?: string[]
    hydration_support?: ('humectant'|'water_loss_reduction')[]
    match_count: number
    ranking_tie_count: number
    ranking_group: string
    matches: {
      metric_code: MetricCode
      metric_name: string
      ingredients: string[]
      evidence_urls: string[]
      rule_details: RuleExplanation[]
      interpretation?: {
        match_basis: string
        metric_assumption: string
        assumption_status: 'development_assumption'
        unverified_items: string[]
        product_efficacy_verified: false
      }
    }[]
    daily_care_ingredients?: string[]
    daily_care_rules?: RuleExplanation[]
    shared_evidence_groups?: { evidence_url: string; metric_codes: MetricCode[]; explanation: string }[]
    recommendation_reason: string
    bundle_suspected: boolean
    usage_mode: 'leave_on_candidate' | 'rinse_off' | 'uncertain'
    usage_basis: string
  }[]
  stats: {
    total_products: number
    unsupported_category: number
    incomplete_ingredients: number
    excluded_by_usage: number
    excluded_by_ingredient: number
    no_matching_metric: number
    no_daily_care_ingredient?: number
    eligible_products: number
  }
  notices: string[]
  empty_reason: string | null
}

export function getCosmeticPreview(body: PreviewRequest, signal?: AbortSignal) {
  return api<PreviewResponse>('/cosmetics/recommendations/preview', {
    method: 'POST', body: JSON.stringify(body), signal,
  })
}
