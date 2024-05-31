import { Component, OnInit } from '@angular/core';
import { NvmeofService } from '../nvmeof.service';
import { NvmeofGateway } from '~/app/shared/models/nvmeof-tcp';

@Component({
  selector: 'cd-nvmeof-overview',
  templateUrl: './nvmeof-overview.component.html',
  styleUrls: ['./nvmeof-overview.component.scss']
})
export class NvmeofOverviewComponent implements OnInit {
  gateways: NvmeofGateway[] = [];
  gatewayColumns: any;

  constructor(private nvmeofService: NvmeofService) {}

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
  }

  getGateways() {
    this.nvmeofService.listGateways().subscribe((gateways: NvmeofGateway[] | NvmeofGateway) => {
      if (Array.isArray(gateways)) this.gateways = gateways;
      else this.gateways = [gateways];
    });
  }
}
