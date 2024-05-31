import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { NvmeofService } from '../nvmeof.service';
import { NvmeofSubsystem } from '~/app/shared/models/nvmeof';
import { ActionLabelsI18n } from '~/app/shared/constants/app.constants';
import { URLBuilderService } from '~/app/shared/services/url-builder.service';
import { CellTemplate } from '~/app/shared/enum/cell-template.enum';
import { CdTableAction } from '~/app/shared/models/cd-table-action';
import { Icons } from '~/app/shared/enum/icons.enum';
import { CdTableSelection } from '~/app/shared/models/cd-table-selection';
import { ListWithDetails } from '~/app/shared/classes/list-with-details.class';
import { CdTableFetchDataContext } from '~/app/shared/models/cd-table-fetch-data-context';
import { AuthStorageService } from '~/app/shared/services/auth-storage.service';
import { Permission } from '~/app/shared/models/permissions';

const BASE_URL = 'nvmeof';

@Component({
  selector: 'cd-nvmeof-subsystems-list',
  templateUrl: './nvmeof-subsystems-list.component.html',
  styleUrls: ['./nvmeof-subsystems-list.component.scss'],
  providers: [{ provide: URLBuilderService, useValue: new URLBuilderService(BASE_URL) }]
})
export class NvmeofSubsystemsListComponent extends ListWithDetails implements OnInit {
  subsystems: NvmeofSubsystem[] = [];
  subsystemsColumns: any;
  selection = new CdTableSelection();
  tableActions: CdTableAction[];
  permission: Permission;

  constructor(
    private nvmeofService: NvmeofService,
    public actionLabels: ActionLabelsI18n,
    private router: Router,
    private urlBuilder: URLBuilderService,
    private authStorageService: AuthStorageService
  ) {
    super();
    this.permission = this.authStorageService.getPermissions().nvmeof;
  }

  ngOnInit() {
    this.subsystemsColumns = [
      {
        name: $localize`Subsystem NQN`,
        prop: 'nqn'
      },
      {
        name: $localize`HA`,
        prop: 'enable_ha',
        cellTransformation: CellTemplate.checkIcon
      },
      {
        name: $localize`Namespace Count`,
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
        click: () => this.router.navigate([this.urlBuilder.getCreate()])
      },
      {
        name: this.actionLabels.EDIT,
        permission: 'update',
        icon: Icons.edit,
        click: () =>
          this.router.navigate([this.urlBuilder.getEdit(String(this.selection.first().id))])
      }
    ];
  }

  getSubsystems(context: CdTableFetchDataContext) {
    this.nvmeofService.listSubsystems().subscribe(
      (subsystems: NvmeofSubsystem[] | NvmeofSubsystem) => {
        if (Array.isArray(subsystems)) this.subsystems = subsystems;
        else this.subsystems = [subsystems];
      },
      () => {
        context.error();
      }
    );
  }
}
