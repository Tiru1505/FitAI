import { useState } from "react";

import { errorMessage } from "../api/client";
import { useAcknowledgeSafety, useNotices } from "../api/hooks";
import { Alert, Button, Card, Spinner } from "./ui";

export function SafetyNotice() {
  const notices = useNotices();
  const ack = useAcknowledgeSafety();
  const [checked, setChecked] = useState(false);

  return (
    <Card title="Before your first workout">
      {notices.isLoading && <Spinner />}
      {notices.data && (
        <div className="space-y-4 text-sm text-beige-200">
          <Alert tone="warning" title="Safety">{notices.data.safety}</Alert>
          <Alert tone="info" title="Camera and privacy">{notices.data.privacy}</Alert>
          <ul className="list-disc space-y-1 pl-5">
            <li>Clear the space around you and use a stable, non-slip surface.</li>
            <li>Warm up first and choose a range of motion you can control.</li>
            <li>Use the <strong>Stop session</strong> button at any time. The camera stops immediately.</li>
            <li>Feedback is automated and can be wrong. Trust how your body feels over the app.</li>
          </ul>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
            <span>I have read and understood this safety and privacy information.</span>
          </label>
          {ack.isError && <Alert tone="error">{errorMessage(ack.error)}</Alert>}
          <Button disabled={!checked || ack.isPending} onClick={() => ack.mutate()}>
            {ack.isPending ? "Saving…" : "Continue"}
          </Button>
        </div>
      )}
    </Card>
  );
}
