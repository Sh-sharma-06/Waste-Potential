import PreviewSectors from "@/components/preview/PreviewSectors";

// The glass-structure sector selection from the design preview, in the main site's typeface.
export default function ExplorePage() {
  return <PreviewSectors homeHref="/" showPreviewChip={false} typeface="classic" />;
}
