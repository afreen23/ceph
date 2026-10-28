import { Component, inject, Input } from '@angular/core';

import { Observable } from 'rxjs';

import { HardwareService } from '~/app/shared/api/hardware.service';
import { Permissions } from '~/app/shared/models/permissions';

@Component({
  selector: 'cd-host-details',
  templateUrl: './host-details.component.html',
  styleUrls: ['./host-details.component.scss'],
  standalone: false
})
export class HostDetailsComponent {
  @Input()
  permissions: Permissions;

  @Input()
  selection: any;

  hardwareEnabled$: Observable<boolean> = inject(HardwareService).isHardwareMonitoringEnabled$;

  get selectedHostname(): string {
    return this.selection !== undefined ? this.selection['hostname'] : null;
  }
}
