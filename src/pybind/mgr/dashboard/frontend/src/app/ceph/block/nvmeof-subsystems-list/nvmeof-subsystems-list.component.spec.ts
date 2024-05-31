import { ComponentFixture, TestBed } from '@angular/core/testing';

import { NvmeofSubsystemsListComponent } from './nvmeof-subsystems-list.component';

describe('NvmeofSubsystemsListComponent', () => {
  let component: NvmeofSubsystemsListComponent;
  let fixture: ComponentFixture<NvmeofSubsystemsListComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [NvmeofSubsystemsListComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(NvmeofSubsystemsListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
