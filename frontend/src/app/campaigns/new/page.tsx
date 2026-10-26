"use client";
import { useRouter } from "next/navigation";
import CampaignForm from "@/components/CampaignForm";
import Shell from "@/components/Shell";
import { PageHeader } from "@/components/ui";

export default function NewCampaign() {
  const router = useRouter();
  return (<Shell><PageHeader title="New campaign" /><CampaignForm onSaved={(c) => router.push(`/campaigns/${c.id}`)} /></Shell>);
}
