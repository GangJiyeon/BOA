// 사진 세트 교체 시 버전을 갱신해 브라우저의 기존 사진 캐시를 무효화한다.
const FEMALE_HAIR_VERSION = '07dc49fb51ed'
const MALE_HAIR_VERSION = '0f64bcb8dd84'
export function hairImageUrl(url: string): string {
  if (/^\/static\/hair\/F\d{3}\.jpg$/.test(url)) return `${url}?v=${FEMALE_HAIR_VERSION}`
  if (/^\/static\/hair\/M\d{3}\.jpg$/.test(url)) return `${url}?v=${MALE_HAIR_VERSION}`
  return url
}
