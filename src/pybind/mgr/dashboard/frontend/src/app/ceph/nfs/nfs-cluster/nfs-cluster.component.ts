import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { BehaviorSubject, Observable, forkJoin, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

import { NfsService } from '~/app/shared/api/nfs.service';
import { OrchestratorService } from '~/app/shared/api/orchestrator.service';
import { DeleteConfirmationModalComponent } from '~/app/shared/components/delete-confirmation-modal/delete-confirmation-modal.component';
import { ActionLabelsI18n, URLVerbs } from '~/app/shared/constants/app.constants';
import { Icons } from '~/app/shared/enum/icons.enum';
import { CellTemplate } from '~/app/shared/enum/cell-template.enum';
import { CdTableAction } from '~/app/shared/models/cd-table-action';
import { CdTableColumn } from '~/app/shared/models/cd-table-column';
import { CdTableSelection } from '~/app/shared/models/cd-table-selection';
import { FinishedTask } from '~/app/shared/models/finished-task';
import { OrchestratorStatus } from '~/app/shared/models/orchestrator.interface';
import { Permission } from '~/app/shared/models/permissions';
import { AuthStorageService } from '~/app/shared/services/auth-storage.service';
import { ModalCdsService } from '~/app/shared/services/modal-cds.service';
import { TaskWrapperService } from '~/app/shared/services/task-wrapper.service';
import { URLBuilderService } from '~/app/shared/services/url-builder.service';

import { NFSBackend, NFSCluster, NFSShare } from '../models/nfs.model';

interface NFSClusterRow extends NFSCluster {
  status: string;
  shares: number;
  protocol: string;
}

const BASE_URL = 'cephfs/nfs/cluster';

@Component({
  selector: 'cd-nfs-cluster',
  templateUrl: './nfs-cluster.component.html',
  styleUrls: ['./nfs-cluster.component.scss'],
  providers: [{ provide: URLBuilderService, useValue: new URLBuilderService(BASE_URL) }],
  standalone: false
})
export class NfsClusterComponent implements OnInit {
  columns: CdTableColumn[] = [];
  tableActions: CdTableAction[] = [];
  selection: CdTableSelection = new CdTableSelection();
  permission: Permission;
  orchStatus: OrchestratorStatus;
  clusters$: Observable<NFSClusterRow[]>;
  subject = new BehaviorSubject<NFSClusterRow[]>([]);

  private destroyRef = inject(DestroyRef);
  public actionLabels = inject(ActionLabelsI18n);
  private authStorageService = inject(AuthStorageService);
  private nfsService = inject(NfsService);
  private orchService = inject(OrchestratorService);
  private urlBuilder = inject(URLBuilderService);
  private router = inject(Router);
  private modalService = inject(ModalCdsService);
  private taskWrapper = inject(TaskWrapperService);

  readonly CLUSTER_PATH = 'nfs/cluster';

  constructor() {
    this.permission = this.authStorageService.getPermissions().nfs;
  }

  ngOnInit(): void {
    this.orchService
      .status()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((status: OrchestratorStatus) => {
        this.orchStatus = status;
      });
    this.clusters$ = this.subject.pipe(
      switchMap(() =>
        forkJoin({
          clusters: this.nfsService.listClusters(true).pipe(
            catchError(() =>
              this.nfsService.listClusters(false).pipe(
                map((names) =>
                  names.map(
                    (name) =>
                      ({
                        name,
                        virtual_ip: null,
                        backend: [],
                        placement: {}
                      }) as NFSCluster
                  )
                ),
                catchError(() => of([] as NFSCluster[]))
              )
            )
          ),
          exports: this.nfsService.list().pipe(
            map((shares) => (Array.isArray(shares) ? shares : []) as NFSShare[]),
            catchError(() => of([] as NFSShare[]))
          )
        }).pipe(map(({ clusters, exports }) => this.mapClusterRows(clusters, exports)))
      )
    );
    this.loadData();
    this.columns = [
      {
        name: $localize`Name`,
        prop: 'name',
        flexGrow: 1
      },
      {
        name: $localize`Status`,
        prop: 'status',
        flexGrow: 1,
        cellTransformation: CellTemplate.tag,
        customTemplateConfig: {
          map: {
            Running: { class: 'tag-success' },
            Degraded: { class: 'tag-warning' },
            Stopped: { class: 'tag-danger' },
            Unknown: { class: 'tag-default' }
          }
        }
      },
      {
        name: $localize`Shares`,
        prop: 'shares',
        flexGrow: 1
      },
      {
        name: $localize`Protocol`,
        prop: 'protocol',
        flexGrow: 1
      }
    ];
    this.tableActions = [
      {
        name: `${this.actionLabels.CREATE} cluster`,
        permission: 'create',
        icon: Icons.add,
        click: () => this.router.navigateByUrl(this.urlBuilder.getCreate()),
        canBePrimary: (selection: CdTableSelection) => !selection.hasSingleSelection
      },
      {
        name: this.actionLabels.DELETE,
        permission: 'delete',
        icon: Icons.destroy,
        click: () => this.removeNFSClusterModal(),
        canBePrimary: (selection: CdTableSelection) => selection.hasSingleSelection
      }
    ];
  }

  removeNFSClusterModal() {
    const cluster = this.selection.first();
    const clusterId = cluster?.name;
    this.modalService.show(DeleteConfirmationModalComponent, {
      itemDescription: $localize`Cluster`,
      itemNames: [clusterId],
      submitActionObservable: () =>
        this.taskWrapper.wrapTaskAroundCall({
          task: new FinishedTask(`${this.CLUSTER_PATH}/${URLVerbs.DELETE}`, {
            cluster_id: clusterId
          }),
          call: this.nfsService.deleteCluster(clusterId)
        })
    });
  }

  private mapClusterRows(clusters: NFSCluster[], exports: NFSShare[]): NFSClusterRow[] {
    const shareCounts = (exports || []).reduce((acc: Record<string, number>, exp: NFSShare) => {
      const clusterId = exp?.cluster_id;
      if (clusterId) {
        acc[clusterId] = (acc[clusterId] || 0) + 1;
      }
      return acc;
    }, {});

    return (clusters || []).map((cluster) => ({
      ...cluster,
      status: this.getClusterStatus(cluster.backend),
      shares: shareCounts[cluster.name] || 0,
      protocol: cluster.enable_nfsv3 ? $localize`NFSv3, NFSv4` : $localize`NFSv4`
    }));
  }

  private getClusterStatus(backends: NFSBackend[] = []): string {
    if (!backends?.length) {
      return '';
    }
    const statuses = backends.map((backend) => (backend.status || '').toLowerCase());
    const running = statuses.filter((status) => status === 'running').length;
    if (running === statuses.length) {
      return 'Running';
    }
    if (running > 0) {
      return 'Degraded';
    }
    return '';
  }

  loadData() {
    this.subject.next([]);
  }

  updateSelection(selection: CdTableSelection) {
    this.selection = selection;
  }
}
