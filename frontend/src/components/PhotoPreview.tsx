import { useEffect, useRef } from 'react'

export default function PhotoPreview({ file }: { file: File }) {
  const image = useRef<HTMLImageElement>(null)
  useEffect(() => {
    const url = URL.createObjectURL(file)
    if (image.current) image.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [file])
  return <figure className="photo-preview">
    <img ref={image} alt={`선택한 사진: ${file.name}`} />
    <figcaption>{file.name}</figcaption>
  </figure>
}
