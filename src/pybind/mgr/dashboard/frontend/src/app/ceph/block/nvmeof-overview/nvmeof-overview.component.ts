import { Component, OnInit } from '@angular/core';
import { NvmeofService } from '../nvmeof.service';
import { NvmeofGateway } from '~/app/shared/models/nvmeof';
import { Permission } from '~/app/shared/models/permissions';
import { AuthStorageService } from '~/app/shared/services/auth-storage.service';
import { CdTableAction } from '~/app/shared/models/cd-table-action';
import { ActionLabelsI18n, URLVerbs } from '~/app/shared/constants/app.constants';
import { ListWithDetails } from '~/app/shared/classes/list-with-details.class';
import { Icons } from '~/app/shared/enum/icons.enum';
import { CdTableSelection } from '~/app/shared/models/cd-table-selection';
import { Router } from '@angular/router';

@Component({
  selector: 'cd-nvmeof-overview',
  templateUrl: './nvmeof-overview.component.html',
  styleUrls: ['./nvmeof-overview.component.scss'],
})
export class NvmeofOverviewComponent extends ListWithDetails implements OnInit {
  gateways: NvmeofGateway[] = [];
  gatewayColumns: any;
  permission: Permission;
  tableActions: CdTableAction[];
  selection = new CdTableSelection();

  constructor(private nvmeofService: NvmeofService, private authStorageService: AuthStorageService,     public actionLabels: ActionLabelsI18n,private router: Router) {
      super();
    this.permission = this.authStorageService.getPermissions().nvmeof;
  }

  ngOnInit() {
    this.gatewayColumns = [
      {
        name: $localize`Name`,
        prop: 'name'
      },
      {
        name: $localize`Address`,
        prop: 'addr'
      },
      {
        name: $localize`Port`,
        prop: 'port'
      }
    ];
    this.tableActions = [
      {
        name: this.actionLabels.CREATE,
        permission: 'create',
        icon: Icons.add,
        click: () => this.openModal(true),
        canBePrimary: (selection: CdTableSelection) => !selection.hasSelection
      },
      {
        name: this.actionLabels.EDIT,
        permission: 'update',
        icon: Icons.edit,
        click: () => this.openModal(false),
      },
      // {
      //   name: this.actionLabels.DELETE,
      //   permission: 'delete',
      //   icon: Icons.add,
      //   click: () => this.deleteAction(),
      //   disable: (selection: CdTableSelection) => this.getDisable('delete', selection)
      // },
    ];
  }

  updateSelection(selection: CdTableSelection) {
    this.selection = selection;
  }

  openModal(hasCreate: boolean) {
    const BASE_URL = 'services';
    if (hasCreate) {
      this.router.navigate([
        BASE_URL,
        {
          outlets: {
            modal: [
              URLVerbs.CREATE,
              'nvmeof',
            ]
          }
        }
      ])
    }
    else {
      const service_id = this.selection.first().name.split('.')[2];
      const service_name = `nvmeof.${service_id}`;
      this.router.navigate([
        BASE_URL,
        {
          outlets: {
            modal: [
              URLVerbs.EDIT,
              'nvmeof',
              service_name
            ]
          }
        }
      ])
    } 
}

  getGateways() {
    this.nvmeofService.listGateways().subscribe((gateways: NvmeofGateway[] | NvmeofGateway) => {
      if (Array.isArray(gateways)) this.gateways = gateways;
      else this.gateways = [gateways];
    });
  }
}
