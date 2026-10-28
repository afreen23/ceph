import { Component, computed, inject, input, TemplateRef, viewChild } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';

import { of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { HardwareService } from '~/app/shared/api/hardware.service';
import { HardwareHealth, HardwareHostResponse } from '~/app/shared/enum/hardware.enum';
import { CdTableColumn } from '~/app/shared/models/cd-table-column';
import { SEVERITY, SeverityIconMap } from '~/app/shared/models/overview';
import { FormatterService } from '~/app/shared/services/formatter.service';

export interface HardwareField {
  label: string;
  value?: string | number | null;
  helperText?: string;
}

/* Drive health, with the same severity icons as the overview page. */
const DRIVE_HEALTH: Record<HardwareHealth, { icon: string; label: string }> = {
  OK: { icon: SeverityIconMap[SEVERITY.ok], label: $localize`OK` },
  Warning: { icon: SeverityIconMap[SEVERITY.warn], label: $localize`Warning` },
  Critical: { icon: SeverityIconMap[SEVERITY.err], label: $localize`Critical` },
  Unknown: { icon: 'infoCircle', label: $localize`Unknown` }
};

/* Readings, in °C, of the temperature sensors with this Redfish PhysicalContext, e.g. 'CPU'. */
function temperatures(report: HardwareHostResponse, context: string): number[] {
  return report.status.temperatures.components
    .filter((sensor) => sensor.physical_context === context)
    .map((sensor) => sensor.reading)
    .filter((reading): reading is number => typeof reading === 'number');
}

/* Hottest sensor with this PhysicalContext, e.g. "52°C". */
function maxTemperature(report: HardwareHostResponse, context: string): string | null {
  const readings = temperatures(report, context);
  return readings.length ? `${Math.round(Math.max(...readings))}°C` : null;
}

@Component({
  selector: 'cd-host-hardware',
  templateUrl: './host-hardware.component.html',
  styleUrls: ['./host-hardware.component.scss'],
  standalone: false
})
export class HostHardwareComponent {
  private readonly hardwareService = inject(HardwareService);
  private readonly formatter = inject(FormatterService);

  readonly hostname = input.required<string>();

  /* The host's hardware report: undefined while loading, null when the host has none. */
  readonly hardware = toSignal(
    toObservable(this.hostname).pipe(
      switchMap((hostname) =>
        this.hardwareService.getHost(hostname).pipe(
          catchError((error) => {
            // A host without node-proxy data is expected: show no hardware, not an error.
            if (error?.status === 404) {
              error.preventDefault?.();
            }
            return of(null);
          })
        )
      )
    )
  );

  readonly fields = computed(() => {
    const report = this.hardware();
    return report ? this.buildFields(report) : [];
  });
  /* Drive ids are only unique within a chassis. */
  readonly drives = computed(() =>
    (this.hardware()?.status.storage.components ?? []).map((drive) => ({
      ...drive,
      uid: `${drive.chassis_id}/${drive.id}`
    }))
  );

  private readonly driveHealthTpl = viewChild.required<TemplateRef<unknown>>('driveHealthTpl');
  readonly driveColumns = computed<CdTableColumn[]>(() => [
    { name: $localize`Device`, prop: 'id', flexGrow: 2 },
    { name: $localize`Type`, prop: 'protocol', flexGrow: 2 },
    { name: $localize`Model`, prop: 'model', flexGrow: 2 },
    { name: $localize`Firmware`, prop: 'firmware_version', flexGrow: 1 },
    { name: $localize`Health`, prop: 'health', flexGrow: 1, cellTemplate: this.driveHealthTpl() }
  ]);
  readonly driveHealth = DRIVE_HEALTH;

  private buildFields(report: HardwareHostResponse): HardwareField[] {
    const fields: HardwareField[] = [
      { label: $localize`CPU temperature`, value: maxTemperature(report, 'CPU') },
      { label: $localize`Drive temperature`, value: maxTemperature(report, 'StorageDevice') },
      { label: $localize`Drives`, value: report.status.storage.total },
      // Installed firmware, under the names the BMC reports, e.g. BIOS or iDRAC.
      ...Object.entries(report.firmware ?? {}).map(([name, version]) => ({
        label: name,
        value: version
      }))
    ];
    const compression = report.compression;
    if (compression) {
      const savings = compression.savings_bytes;
      const ratio = compression.compression_ratio;
      // Both are null until the FCM drives hold enough data.
      const helperText =
        ratio === null
          ? $localize`Needs at least 100 GiB of data on the FCM drives to be shown.`
          : undefined;
      fields.push(
        {
          label: $localize`Savings`,
          value: savings === null ? null : this.formatter.formatToBinary(savings, false, 1),
          helperText
        },
        {
          label: $localize`Compression ratio`,
          value: ratio === null ? null : `${ratio}:1`,
          helperText
        }
      );
    }
    return fields;
  }
}
