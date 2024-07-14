import { Component, Input, OnChanges } from '@angular/core';
import { CdTableColumn } from '~/app/shared/models/cd-table-column';
import { NvmeofSubsystem, NvmeofSubsystemHost } from '~/app/shared/models/nvmeof';

@Component({
  selector: 'cd-nvmeof-subsystems-details',
  templateUrl: './nvmeof-subsystems-details.component.html',
  styleUrls: ['./nvmeof-subsystems-details.component.scss']
})
export class NvmeofSubsystemsDetailsComponent implements OnChanges {
  @Input()
  selection: NvmeofSubsystem;

  selectedItem: any;
  data: any;

  initiators: NvmeofSubsystemHost[] = [];
  initiatorsCount: any;
  initiatorsColumns: CdTableColumn[];

  constructor() {
    this.initiatorsColumns = [
      {
        name: $localize`Initiator`,
        prop: 'nqn'
      }
    ];
  }

  ngOnChanges() {
    if (this.selection) {
      this.selectedItem = this.selection;

      this.initiators = this.selectedItem.initiators;
      if (this.initiators[0].nqn === '*') {
        this.initiators[0].nqn = $localize`Allow all hosts`;
        this.initiatorsCount = '*';
      } else this.initiatorsCount = this.initiators.length;

      this.data = {};
      this.data[$localize`Serial Number`] = this.selectedItem.serial_number;
      this.data[$localize`Model Number`] = this.selectedItem.model_number;
      this.data[$localize`Minimum Controller Identifier`] = this.selectedItem.min_cntlid;
      this.data[$localize`Maximum Controller Identifier`] = this.selectedItem.max_cntlid;
      this.data[$localize`Subsystem Type`] = this.selectedItem.subtype;
    }
  }
}
