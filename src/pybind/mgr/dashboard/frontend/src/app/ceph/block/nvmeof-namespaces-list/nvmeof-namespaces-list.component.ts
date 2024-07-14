import { Component, Input, OnChanges, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { NvmeofService } from '~/app/shared/api/nvmeof.service';
import { CriticalConfirmationModalComponent } from '~/app/shared/components/critical-confirmation-modal/critical-confirmation-modal.component';
import { ActionLabelsI18n, URLVerbs } from '~/app/shared/constants/app.constants';
import { Icons } from '~/app/shared/enum/icons.enum';
import { CdTableAction } from '~/app/shared/models/cd-table-action';
import { CdTableSelection } from '~/app/shared/models/cd-table-selection';
import { FinishedTask } from '~/app/shared/models/finished-task';
import { NvmeofSubsystemNamespace } from '~/app/shared/models/nvmeof';
import { Permission } from '~/app/shared/models/permissions';
import { AuthStorageService } from '~/app/shared/services/auth-storage.service';
import { ModalService } from '~/app/shared/services/modal.service';
import { TaskWrapperService } from '~/app/shared/services/task-wrapper.service';

const BASE_URL = 'block/nvmeof/subsystems';

@Component({
  selector: 'cd-nvmeof-namespaces-list',
  templateUrl: './nvmeof-namespaces-list.component.html',
  styleUrls: ['./nvmeof-namespaces-list.component.scss']
})
export class NvmeofNamespacesListComponent implements OnInit, OnChanges {
  @Input()
  subsystemNQN: string;

  namespacesColumns: any;
  tableActions: CdTableAction[];
  selection = new CdTableSelection();
  permission: Permission;
  namespaces: NvmeofSubsystemNamespace[];

  constructor(
    public actionLabels: ActionLabelsI18n,
    private router: Router,
    private modalService: ModalService,
    private authStorageService: AuthStorageService,
    private taskWrapper: TaskWrapperService,
    private nvmeofService: NvmeofService
  ) {
    this.permission = this.authStorageService.getPermissions().nvmeof;
  }

  ngOnInit() {
    this.namespacesColumns = [
      {
        name: $localize`ID`,
        prop: 'nsid'
      },
      {
        name: $localize`UUID`,
        prop: 'uuid'
      },
      {
        name: $localize`Image`,
        prop: 'bdev_name'
      },
      {
        name: $localize`Image Size`,
        prop: 'rbd_image_size'
      },
      {
        name: $localize`Block Size`,
        prop: 'block_size'
      },
      {
        name: $localize`RW IOPS`,
        prop: 'rw_ios_per_second'
      },
      {
        name: $localize`RW MB/s`,
        prop: 'rw_mbytes_per_second'
      },
      {
        name: $localize`R MB/s`,
        prop: 'r_mbytes_per_second'
      },
      {
        name: $localize`W MB/s`,
        prop: 'w_mbytes_per_second'
      },
      {
        name: $localize`Load Balancing Group`,
        prop: 'load_balancing_group'
      }
    ];
    this.tableActions = [
      {
        name: this.actionLabels.CREATE,
        permission: 'create',
        icon: Icons.add,
        click: () => this.router.navigate([BASE_URL, { outlets: { modal: [URLVerbs.CREATE] } }]),
        canBePrimary: (selection: CdTableSelection) => !selection.hasSelection
      },
      {
        name: this.actionLabels.EDIT,
        permission: 'update',
        icon: Icons.edit,
        click: () =>
          this.router.navigate([
            BASE_URL,
            {
              outlets: {
                modal: [
                  URLVerbs.EDIT,
                  this.selection.first().nqn,
                  this.selection.first().max_namespaces
                ]
              }
            }
          ])
      },
      {
        name: this.actionLabels.DELETE,
        permission: 'delete',
        icon: Icons.destroy,
        click: () => this.deleteSubsystemModal()
      }
    ];
  }

  ngOnChanges() {
    this.listNamespaces();
  }

  updateSelection(selection: CdTableSelection) {
    this.selection = selection;
  }

  listNamespaces() {
    this.nvmeofService
      .listNamespaces(this.subsystemNQN)
      .subscribe((res: NvmeofSubsystemNamespace[]) => {
        this.namespaces = res;
      });
  }

  deleteSubsystemModal() {
    const subsystem = this.selection.first();
    this.modalService.show(CriticalConfirmationModalComponent, {
      itemDescription: 'Subsystem',
      itemNames: [subsystem.nqn],
      actionDescription: 'delete',
      submitActionObservable: () =>
        this.taskWrapper.wrapTaskAroundCall({
          task: new FinishedTask('nvmeof/subsystem/delete', { nqn: subsystem.nqn }),
          call: this.nvmeofService.deleteSubsystem(subsystem.nqn)
        })
    });
  }
}
