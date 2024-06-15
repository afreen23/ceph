import { Component } from '@angular/core';
import { NvmeofService } from '../nvmeof.service';
import { NvmeofSubsystem } from '~/app/shared/models/nvmeof';
import { CellTemplate } from '~/app/shared/enum/cell-template.enum';
import { CdTableAction } from '~/app/shared/models/cd-table-action';
import { ActionLabelsI18n } from '~/app/shared/constants/app.constants';
import { Icons } from '~/app/shared/enum/icons.enum';
import { Router } from '@angular/router';
import { CdTableSelection } from '~/app/shared/models/cd-table-selection';
import { URLBuilderService } from '~/app/shared/services/url-builder.service';

const BASE_URL = 'subsystems';

@Component({
  selector: 'cd-nvmeof-subsystems-list',
  templateUrl: './nvmeof-subsystems-list.component.html',
  styleUrls: ['./nvmeof-subsystems-list.component.scss'],
  providers: [{ provide: URLBuilderService, useValue: new URLBuilderService(BASE_URL) }],
})
export class NvmeofSubsystemsListComponent {
  subsytems: NvmeofSubsystem[] = [];
  subsystemsColumns: any;
  tableActions: CdTableAction[];
  selection = new CdTableSelection();

  constructor(
    private nvmeofService: NvmeofService,
    public actionLabels: ActionLabelsI18n,
    private urlBuilder: URLBuilderService,
    private router: Router,
  ) {}

  ngOnInit() {
    this.subsystemsColumns = [
      {
        name: $localize`Subsystem NQN`,
        prop: 'nqn'
      },
      {
        name: $localize`HA Enabled`,
        prop: 'enable_ha',
        cellTransformation: CellTemplate.checkIcon,
      },
      {
        name: $localize`Namespace count`,
        prop: 'namespace_count'
      },
      {
        name: $localize`Maximum Namespaces`,
        prop: 'max_namespaces'
      }
    ];
    this.tableActions = [
      {
        name: this.actionLabels.CREATE,
        permission: 'create',
        icon: Icons.add,
        click: () => this.router.navigate([this.urlBuilder.getCreate()]),
        canBePrimary: (selection: CdTableSelection) => !selection.hasSelection
      },
      {
        name: this.actionLabels.EDIT,
        permission: 'update',
        icon: Icons.edit,
        click: () =>
          this.router.navigate([this.urlBuilder.getEdit(String(this.selection.first().id))])
      },
    ];
  }

  getSubsystems() {
    this.nvmeofService.listSubsystems().subscribe((subsytems: NvmeofSubsystem[] | NvmeofSubsystem) => {
      if (Array.isArray(subsytems)) this.subsytems = subsytems;
      else this.subsytems = [subsytems];
    });
  }
}
